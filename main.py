import aiohttp, asyncio, json, os, time, uuid
from itertools import islice, cycle

class sniper:
    def __init__(self):
        self.account = asyncio.run(self.setup_accounts())
        with open('config.json', 'r') as file: 
            content = json.load(file)
            self.items = content['items']
            self.key = content['key']
        self.errorLogs = []
        self.buyLogs = []
        self.searchLogs = []
        self.clear = "cls" if os.name == 'nt' else "clear"
        self.totalSearches = 0
        asyncio.run(self.auto_search())
    
    async def auto_search(self):
        async with aiohttp.ClientSession(headers={"key": self.key}) as client:
            response = await client.post("https://mycock.amaishn.repl.co/get_items", ssl = False)
            if response.status == 200:
               self.items['list'].update(await response.json())
        
    async def setup_accounts(self):
        with open('config.json', 'r') as file: cookie = (json.load(file))['cookie']
        return {"cookie": cookie, "xcsrf_token": await self._get_xcsrf_token(cookie), "user_id": await self._get_user_id(cookie)}

    async def _get_user_id(self, cookie) -> str:
       async with aiohttp.ClientSession(cookies={".ROBLOSECURITY": cookie}) as client:
           response = await client.get("https://users.roblox.com/v1/users/authenticated", ssl = False)
           data = await response.json()
           if data.get('id') == None:
              raise Exception("Couldn't scrape user id. Error:", data)
           return data.get('id')
       
    async def _get_xcsrf_token(self, cookie) -> dict:
        async with aiohttp.ClientSession(cookies={".ROBLOSECURITY": cookie}) as client:
              response = await client.post("https://accountsettings.roblox.com/v1/email", ssl = False)
              xcsrf_token = response.headers.get("x-csrf-token")
              if xcsrf_token is None:
                 raise Exception("An error occurred while getting the X-CSRF-TOKEN. "
                            "Could be due to an invalid Roblox Cookie")
              return xcsrf_token
    
    async def buy_item(self, session, info):
         data = {
               "collectibleItemId": info["collectibleItemId"],
               "expectedCurrency": 1,
               "expectedPrice": info['price'],
               "expectedPurchaserId": self.account['user_id'],
               "expectedPurchaserType": "User",
               "expectedSellerId": info["creator"],
               "expectedSellerType": "User",
               "idempotencyKey": str(uuid.uuid4()),
               "collectibleProductId": info['productid_data'],
               "collectibleItemInstanceId": info['collectibleItemInstanceId']
         }
         try:
            async with session.post(f"https://apis.roblox.com/marketplace-sales/v1/item/{info['collectibleItemId']}/purchase-resale",
                                 json=data,
                                 headers={"x-csrf-token": self.account['xcsrf_token'], 'Accept-Encoding': 'gzip'},
                                 cookies={".ROBLOSECURITY": self.account['cookie']}, ssl = False) as response:
                if response.status == 200:
                    resp = await response.json()
                    if not resp.get("purchased"):
                        self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Failed to buy item {info['item_id']}, reason: {resp.get('errorMessage')}")
                        del self.items['list'][info['item_id']]
                        return
                    self.buyLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Bought item {info['item_id']} for a price of {info['price']}")
                    return
                else:
                    self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Failed to buy item {info['item_id']}")
                    return
         except Exception as e:
            self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {e}")
             
    
    async def search(self):
        cycler = cycle(list(self.items['list'].keys()))
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=None), timeout=aiohttp.ClientTimeout(total=None)) as session: 
            while True:
                try:
                    items = {k: self.items['list'][k] for k in islice(cycler, 120)}
                    async with session.post("https://catalog.roblox.com/v1/catalog/items/details",
                                           json={"items": [{"itemType": "Asset", "id": id} for id in items]},
                                           headers={"x-csrf-token": self.account['xcsrf_token'], 'Accept-Encoding': 'gzip'},
                                           cookies={".ROBLOSECURITY": self.account['cookie']}, ssl=False) as response:
                        if response.status == 200:
                            self.searchLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Searched total of {len(self.items['list'])} items")
                            json_rep = await response.json()
                            for item in json_rep['data']:
                                info = {"creator": None, "price": int(item.get("lowestResalePrice", 999999999)), "productid_data": None, "collectibleItemId": item.get("collectibleItemId"), "item_id": str(item.get("id"))}
                                if not item.get("hasResellers") or info["price"] > self.items['global_max_price'] or info["price"] > self.items['list'][str(info["item_id"])]['id']:
                                    continue
                                async with await session.get(f"https://apis.roblox.com/marketplace-sales/v1/item/{info['collectibleItemId']}/resellers?limit=1",
                                                            headers={"x-csrf-token": self.account['xcsrf_token'], 'Accept': "application/json", 'Accept-Encoding': 'gzip'},
                                                            cookies={".ROBLOSECURITY": self.account['cookie']}, ssl=False) as resell:
                                    resell_user = (await resell.json())["data"][0]
                                    info["productid_data"] = resell_user["collectibleProductId"]
                                    info["creator"] = resell_user["seller"]["sellerId"]
                                    info["collectibleItemInstanceId"] = resell_user["collectibleItemInstanceId"]
                                await self.buy_item(session, info)
                                
                        elif response.status == 403:
                            if (await response.json())['message'] == "Token Validation Failed":
                                self.account['xcsrf_token'] = await self._get_xcsrf_token(self.account['cookie'])
                                continue
                        elif response.status == 429:
                            self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Ratelimit hit")
                            await asyncio.sleep(5)         
                except Exception as e:
                    self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {e}")
                finally:
                    os.system(self.clear)
                    self.totalSearches += 1
                    print("Total Searches: " + repr(self.totalSearches) + "\n\nSearch Logs:\n" + '\n'.join(log for log in self.searchLogs[-3:]) + f"\n\nBuy Logs:\nTotal Items bought: {len(self.buyLogs)}\n" + '\n'.join(log for log in self.buyLogs[-5:]) + "\n\nError Logs:\n" + '\n'.join(log for log in self.errorLogs[-5:]))
                    await asyncio.sleep(1)
  
asyncio.run(sniper().search())
