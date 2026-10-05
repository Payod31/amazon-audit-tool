from src.core.marketplaces import load_marketplaces, get_marketplace, is_rtl

all_mp = load_marketplaces()
print(f"Loaded {len(all_mp)} marketplaces:\n")
for key, mp in all_mp.items():
    print(f"{key:12} {mp['country']:22} {mp['domain']:16} {mp['currency']}  languages={mp['languages']}")

sa = get_marketplace("amazon_sa")
print("\nSaudi Arabic is right-to-left:", is_rtl(sa, "ar-SA"))