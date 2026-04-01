import asyncio
import time
import aiohttp

URL = "http://localhost:5001/process"
FILE_PATH = "test.pdf"

TOTAL_REQUESTS = 10
MAX_CONCURRENT = 10
TIMEOUT = 120

# 👉 Your API key must match the server's API_KEY env variable
API_KEY = "secret"  # change this if needed


async def upload(session, i, semaphore):
    async with semaphore:
        start = time.time()
        print(f"[{i}] 🚀 START")

        try:
            with open(FILE_PATH, "rb") as f:
                data = aiohttp.FormData()
                data.add_field("file", f, filename="test.pdf", content_type="application/pdf")

                async with session.put(
                    URL,
                    data=data,
                    timeout=TIMEOUT,
                    headers={"Authorization": f"Bearer {API_KEY}"},
                ) as resp:

                    duration = time.time() - start

                    if resp.status != 200:
                        print(f"[{i}] ❌ Status {resp.status} ({duration:.2f}s)")
                        return False

                    json_data = await resp.json()
                    print(json_data)

                    if not isinstance(json_data, list):
                        print(f"[{i}] ❌ Invalid response ({duration:.2f}s)")
                        return False

                    print(f"[{i}] ✅ DONE ({duration:.2f}s)")
                    return True

        except asyncio.TimeoutError:
            print(f"[{i}] ⏱️ TIMEOUT")
            return False
        except Exception as e:
            print(f"[{i}] ❌ ERROR: {e}")
            return False


async def main():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            upload(session, i, semaphore)
            for i in range(TOTAL_REQUESTS)
        ]

        start = time.time()
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start

        success = sum(results)
        failed = len(results) - success

        print("\n--- RESULTS ---")
        print(f"Total requests: {len(results)}")
        print(f"Success: {success}")
        print(f"Failed: {failed}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Req/sec: {len(results)/total_time:.2f}")


if __name__ == "__main__":
    asyncio.run(main())