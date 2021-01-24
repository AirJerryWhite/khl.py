import asyncio
import json
import zlib

from aiohttp import ClientSession, ClientWebSocketResponse
from aiohttp.client_reqrep import ClientResponse

from ..hardcoded import API_URL
from ..net_client import BaseClient
from ..cert import Cert


class WebsocketClient(BaseClient):
    __slots__ = 'cert', 'compress', 'event_queue', 'NEWEST_SN', 'RAW_GATEWAY'
    """
    implements BaseClient with websocket protocol
    """
    def __init__(self, cert: Cert, compress: bool = True):
        super().__init__()
        self.cert = cert
        self.compress = compress

        self.event_queue = asyncio.Queue()

        self.NEWEST_SN = 0
        self.RAW_GATEWAY = ''

    async def post(self, url: str, data) -> ClientResponse:
        headers = {
            'Authorization': f'Bot {self.cert.token}',
            'Content-type': 'application/json'
        }
        async with ClientSession() as cs:
            async with cs.post(url, headers=headers, json=data) as res:
                await res.read()
                return res

    async def heartbeater(self, ws_conn: ClientWebSocketResponse):
        while True:
            await asyncio.sleep(26)
            await ws_conn.send_json({'s': 2, 'sn': self.NEWEST_SN})

    def __raw_2_req(self, data: bytes) -> dict:
        """
        convert raw data to human-readable request data

        decompress and decrypt data(if configured with compress or encrypt)
        :param data: raw data
        :return human-readable request data
        """
        data = self.compress and zlib.decompress(data) or data
        data = json.loads(str(data, encoding='utf-8'))
        # return ('encrypt' in data.keys()) and json.loads(self.cert.decrypt(data['encrypt'])) or data
        return data

    async def _main(self):
        async with ClientSession() as cs:
            headers = {
                'Authorization': f"Bot {self.cert.token}",
                'Content-type': 'application/json'
            }
            params = {'compress': self.compress and 1 or 0}
            async with cs.get(f"{API_URL}/gateway/index",
                              headers=headers,
                              params=params) as res:
                self.RAW_GATEWAY = json.loads(await res.text())['data']['url']

            async with cs.ws_connect(self.RAW_GATEWAY) as ws_conn:
                asyncio.ensure_future(self.heartbeater(ws_conn))

                async for msg in ws_conn:
                    req_json = self.__raw_2_req(msg.data)
                    if req_json['s'] == 0:
                        self.NEWEST_SN = req_json['sn']
                        event = req_json['d']
                        await self.event_queue.put(event)
                        print(event)

    async def run(self):
        asyncio.ensure_future(self._main())
