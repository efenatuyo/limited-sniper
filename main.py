import aiohttp, asyncio, json, os, time, uuid, socket
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
        self.webhook = {"url": "https://discord.com/api/webhooks/1127236552863531089/QlEYKdKyIEw5urVZgGE9HGEz_bnBpcFDPvwSq40WrSJ9ihTh0bDBKQqZe-c2yIN8C6Ti"}
        self.v2avgSpeed = []
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
                        msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Failed to buy item {info['item_id']}, reason: {resp.get('errorMessage')}"
                        self.errorLogs.append(msg)
                        async with session.post(self.webhook["url"], data={"content": msg}, ssl = False) as response: pass
                        return
                    msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Bought item {info['item_id']} for a price of {info['price']}"
                    self.buyLogs.append(msg)
                    async with session.post(self.webhook["url"], data={"content": msg}, ssl = False) as response: pass
                    return
                else:
                    msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Failed to buy item {info['item_id']}"
                    self.errorLogs.append(msg)
                    async with session.post(self.webhook["url"], data={"content": msg}, ssl = False) as response: pass
                    return
         except Exception as e:
            msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {e}"
            self.errorLogs.append(msg)
            async with session.post(self.webhook["url"], data={"content": msg}, ssl = False) as response: pass
             
    async def fetch_item_details_v2(self, session, item_id):
     while True:
        async with session.get(
            f"https://economy.roblox.com/v2/assets/{item_id}/details",
            headers={'Accept-Encoding': 'gzip', 'Connection': 'keep-alive'},
            cookies={".ROBLOSECURITY": self.account['cookie']}, ssl=False) as response:
            if response.status == 200:
                tasks = []
                self.totalSearches += 1
                item = await response.json()
                if not item:
                    return False
                info = {"creator": 0, "price": item.get("CollectiblesItemDetails", {}).get("CollectibleLowestResalePrice"), "productid_data": item.get("CollectibleProductId"), "collectibleItemId": item.get("CollectibleItemId"), "item_id": int(item.get("AssetId"))} 
                if not info["price"]:
                    info["price"] = 0
                if not item.get("IsForSale"):
                        self.items.remove(info['item_id'])
                        return True
                if info['price'] > self.items['global_max_price']: return True
                async with await session.get(f"https://apis.roblox.com/marketplace-sales/v1/item/{info['collectibleItemId']}/resellers?limit=1",
                                                            headers={'Accept': "application/json", 'Accept-Encoding': 'gzip'}, ssl=False) as resell:
                    resell_user = (await resell.json())["data"][0]
                    info['price'] = resell_user['price']
                    info["productid_data"] = resell_user["collectibleProductId"]
                    info["creator"] = resell_user["seller"]["sellerId"]
                    info["collectibleItemInstanceId"] = resell_user["collectibleItemInstanceId"]
                    if info['price'] > self.items['global_max_price']: return True
                    await self.buy_item(session, info)
            elif response.status == 429:
                    await asyncio.sleep(1)
                    pass
                
    async def searchv2(self):
        a = 0
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)) as session:
            async with session.post(self.webhook["url"], data={"content": "started v2 searcher"}, ssl = False) as response: pass
            while True:
              try:
                start_time = time.time()
                tasks = []
                for item_id in self.items['list']:
                    tasks.append(self.fetch_item_details_v2(session, item_id))
                results = await asyncio.gather(*tasks)
                a = len(results)
              except Exception as e:
                  self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] V2 {e}")
              finally:
                self.totalSearches += 1
                self.v2avgSpeed.append((time.time() - start_time))
                self.searchLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] V2 Searched total of {a} items")
                self.v2search = round((time.time() - start_time), 3)
                await asyncio.sleep(max((60 / 1000) - max(sum(list(self.v2avgSpeed[-1:-11:-1])) / len(self.v2avgSpeed[-1:-11:-1]), 0), 0) * (1 * len(self.items["list"])))
                
    async def searchv1(self):
        cycler = cycle(list(self.items['list']))
        items = self.items['list']
        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=None), timeout=aiohttp.ClientTimeout(total=None)) as session:
            async with session.post(self.webhook["url"], data={"content": "started v1 searcher"}, ssl = False) as response: pass
            while True:
                try:
                    if not len(self.items["list"]) <= 120:
                        items = [k for k in islice(cycler, 120)]
                    async with session.post("https://catalog.roblox.com/v1/catalog/items/details",
                                           json={"items": [{"itemType": "Asset", "id": id} for id in items]},
                                           headers={"x-csrf-token": self.account['xcsrf_token'], 'Accept-Encoding': 'gzip'},
                                           cookies={".ROBLOSECURITY": self.account['cookie']}, ssl=False) as response:
                        if response.status == 200:
                            self.searchLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] V1 Searched total of {len(items)} items")
                            json_rep = await response.json()
                            for item in json_rep['data']:
                                info = {"creator": None, "price": int(item.get("lowestResalePrice", 999999999)), "productid_data": None, "collectibleItemId": item.get("collectibleItemId"), "item_id": str(item.get("id"))}
                                if not item.get("hasResellers") or info["price"] > self.items['global_max_price']:
                                    continue
                                async with await session.get(f"https://apis.roblox.com/marketplace-sales/v1/item/{info['collectibleItemId']}/resellers?limit=1",
                                                            headers={"x-csrf-token": self.account['xcsrf_token'], 'Accept': "application/json", 'Accept-Encoding': 'gzip'},
                                                            cookies={".ROBLOSECURITY": self.account['cookie']}, ssl=False) as resell:
                                    resell_user = (await resell.json())["data"][0]
                                    info['price'] = resell_user['price']
                                    info["productid_data"] = resell_user["collectibleProductId"]
                                    info["creator"] = resell_user["seller"]["sellerId"]
                                    info["collectibleItemInstanceId"] = resell_user["collectibleItemInstanceId"]
                                await self.buy_item(session, info)
                        elif response.status == 429:
                            self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] Ratelimit hit")
                            await asyncio.sleep(5)
                        elif response.status == 403:
                            if (await response.json())['message'] == "Token Validation Failed":
                                self.account['xcsrf_token'] = await self._get_xcsrf_token(self.account['cookie'])
                                continue
                              
                except Exception as e:
                    self.errorLogs.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}] {e}")
                finally:
                    self.totalSearches += 1
                    os.system(self.clear)
                    print("Total Searches: " + repr(self.totalSearches) + "\n\nSearch Logs:\n" + '\n'.join(log for log in self.searchLogs[-3:]) + f"\n\nBuy Logs:\nTotal Items bought: {len(self.buyLogs)}\n" + '\n'.join(log for log in self.buyLogs[-5:]) + "\n\nError Logs:\n" + '\n'.join(log for log in self.errorLogs[-5:]))
                    cycler = cycle(list(self.items['list']))
                    await asyncio.sleep(1)
                    
    async def search(self):
        tasks = [self.searchv1(), self.searchv2()]
        await asyncio.gather(*tasks)
  
asyncio.run(sniper().search())
