# author: Nikolas Antoniou

# importing necessary libraries
import time
import requests 

# api link: https://api.inaturalist.org/v1/observations?place_id=10289&quality_grade=research&reviewed=true&iconic_taxa=Insecta&photo_license=cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa&photos=true
# source: www.inaturalist.org

# defining the parameters
params = {
    "place_id" : 10289,
    "quality_grade" : "research",
    "photos" :  True,
    "iconic_taxa": ["Insecta"],
    "photo_license" : ["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"],
}

response = requests.get("https://api.inaturalist.org/v1/observations", params=params)
print(response)

# parsing the data
data = response.json()

print(type(data))
print(data["total_results"])
print(len(data["results"]))

# first output: 30 results.
# There is a default of 30 results per page
rows = []
cursor = None

start = time.perf_counter()
seen = 0
total = data["total_results"]    

while True:
    p = {"per_page":200, "place_id":10289, "quality_grade": "research", "iconic_taxa": ["Insecta"], "photos":True, "photo_license" : ["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa"]}
    if cursor is not None:
        p["id_below"] = cursor
        
    r = requests.get("https://api.inaturalist.org/v1/observations", params=p)
    if r.status_code != 200:
        print("Stopped: ", r.status_code)
        break
    
    # batch initialization
    batch = r.json()["results"]
    # if api returns 0 results
    if not batch : break
    
    for item in batch:
        for photo in item.get("photos", []):
            rows.append({
                "observation_id": item["id"],
                "taxon_name": item["taxon"]["name"] if item.get("taxon") else None,
                "photo_url" : photo["url"],
                "license_code": photo["license_code"],
                "attribution": photo["attribution"],
                "location": item.get("place_guess")
            })
    
    seen += len(batch)
    elapsed = time.perf_counter() - start
    rate = seen / elapsed
    eta = (total - seen) / rate if rate else 0
    print(f"\r{seen:,}/{total:,} obs ({seen/total:5.1%}) | "
          f"{len(rows):,} photo rows | {elapsed/60:4.1f} min elapsed | "
          f"~{eta/60:4.1f} min left", end="", flush=True)
    cursor = batch[-1]["id"]
    time.sleep(1) # avoid blocks
    
print()
print(len(rows), "rows")

import pandas as pd 
import os

# saving the dataset
df = pd.DataFrame(rows)
df.to_csv("insects.csv", index=False)