import asyncio
import time
from src.studieplus_scraper import api


async def test_cache_performance():
    print("[*] Testing cache performance improvements...")
    print("=" * 60)

    # Test 1: Schedule caching
    print("\n[TEST 1] Schedule Cache Performance")
    print("-" * 60)

    # First call - no cache (slow)
    print("\nFirst call (no cache):")
    start = time.time()
    result1 = await api.get_full_schedule(week_offset=0)
    elapsed1 = time.time() - start
    print(f"  Time: {elapsed1:.2f}s")
    print(f"  Found {len(result1['lessons'])} lessons for week {result1['week']}")

    # Second call - from cache (fast!)
    print("\nSecond call (from cache):")
    start = time.time()
    result2 = await api.get_full_schedule(week_offset=0)
    elapsed2 = time.time() - start
    print(f"  Time: {elapsed2:.2f}s")
    print(f"  Found {len(result2['lessons'])} lessons for week {result2['week']}")

    speedup = elapsed1 / elapsed2 if elapsed2 > 0.001 else 10000
    print(f"\n[+] Cache speedup: {speedup:.1f}x faster!")
    print(f"    Saved: {elapsed1 - elapsed2:.2f}s")

    # Test 2: Assignments caching
    print("\n" + "=" * 60)
    print("[TEST 2] Assignments Cache Performance")
    print("-" * 60)

    # First call - no cache (slow)
    print("\nFirst call (no cache):")
    start = time.time()
    result1 = await api.get_all_assignments()
    elapsed1 = time.time() - start
    print(f"  Time: {elapsed1:.2f}s")
    print(f"  Found {result1['count']} assignments")

    # Second call - from cache (fast!)
    print("\nSecond call (from cache):")
    start = time.time()
    result2 = await api.get_all_assignments()
    elapsed2 = time.time() - start
    print(f"  Time: {elapsed2:.2f}s")
    print(f"  Found {result2['count']} assignments")

    speedup = elapsed1 / elapsed2 if elapsed2 > 0.001 else 10000
    print(f"\n[+] Cache speedup: {speedup:.1f}x faster!")
    print(f"    Saved: {elapsed1 - elapsed2:.2f}s")

    # Test 3: Multiple rapid calls
    print("\n" + "=" * 60)
    print("[TEST 3] Multiple Rapid Calls")
    print("-" * 60)

    print("\nCalling get_full_schedule() 5 times...")
    start = time.time()
    for i in range(5):
        result = await api.get_full_schedule(week_offset=0)
        print(f"  Call {i+1}: {len(result['lessons'])} lessons")
    elapsed = time.time() - start
    print(f"\nTotal time for 5 calls: {elapsed:.2f}s")
    print(f"Average per call: {elapsed/5:.3f}s")

    print("\n" + "=" * 60)
    print("[+] Cache performance test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_cache_performance())
