import pandas as pd, random
from faker import Faker

fake=Faker()
random.seed(42)

real=pd.read_csv("kathmandu_hostels_precise.csv")
real["hostel_source"]="Real"
real["verified"]="Yes"

areas=[
"Thimi, Bhaktapur","Dhapakhel, Lalitpur","Koteshwor, Kathmandu","Baneshwor, Kathmandu",
"Pulchowk, Lalitpur","Jawalakhel, Lalitpur","Imadol, Lalitpur","Boudha, Kathmandu",
"Chabahil, Kathmandu","Kalanki, Kathmandu","Gwarko, Lalitpur","Satdobato, Lalitpur"
]
prefix=["Everest","Himalayan","Lotus","Royal","Peace","Green","Golden","Buddha","Shree","Valley","Mountain","Om"]
suffix=["Hostel","Student Hostel","Residency","Boys Hostel","Girls Hostel","Student Home","Residence"]

base=real[["latitude","longitude"]].dropna().sample(frac=1,replace=True,random_state=42).reset_index(drop=True)

extra=[]

manual=[
("GPA Girls Hostel","Dhapakhel, Lalitpur","Girls"),
("Om Mangal Murti Hostel","Dhapakhel, Lalitpur","Mixed")
]

for i,(n,loc,g) in enumerate(manual):
    lat=float(base.loc[i,"latitude"])+random.uniform(-0.0015,0.0015)
    lon=float(base.loc[i,"longitude"])+random.uniform(-0.0015,0.0015)
    extra.append({"name":n,"precise_location":loc,"latitude":lat,"longitude":lon,"hostel_source":"Real","verified":"Yes","gender":g})

need=300-(len(real)+len(extra))
for i in range(need):
    lat=float(base.loc[(i+2)%len(base),"latitude"])+random.uniform(-0.002,0.002)
    lon=float(base.loc[(i+2)%len(base),"longitude"])+random.uniform(-0.002,0.002)
    extra.append({
      "name":f"{random.choice(prefix)} {random.choice(suffix)}",
      "precise_location":random.choice(areas),
      "latitude":lat,"longitude":lon,
      "hostel_source":"Generated","verified":"No",
      "gender":random.choice(["Boys","Girls","Mixed"])
    })

extra=pd.DataFrame(extra)

allh=pd.concat([real,extra],ignore_index=True)

defaults={
"monthly_price":lambda: random.randrange(7000,18000,500),
"room_type":lambda: random.choice(["Single","Double","Shared"]),
"wifi":"Yes","food":"Yes","laundry":"Yes","parking":lambda: random.choice(["Yes","No"]),
"attached_bathroom":lambda: random.choice(["Yes","No"]),
"hot_water":"Yes","study_room":"Yes","power_backup":lambda: random.choice(["Yes","No"]),
"cctv":"Yes","curfew":lambda: random.choice(["Yes","No"]),
"rating":lambda: round(random.uniform(3.5,5.0),1),
"review_count":lambda: random.randint(5,40),
"description":"Comfortable student hostel with WiFi, food and study environment."
}
for k,v in defaults.items():
    if k not in allh.columns:
        allh[k]=""
    allh[k]=allh[k].replace("",pd.NA)
    if callable(v):
        allh[k]=allh[k].apply(lambda x:v() if pd.isna(x) else x)
    else:
        allh[k]=allh[k].fillna(v)

allh.insert(0,"id",range(1,len(allh)+1))
allh.to_csv("hostels_final.csv",index=False)

reviews=[]
texts=[
("Very clean rooms and friendly owner.","Positive"),
("Affordable hostel with good WiFi.","Positive"),
("Food quality is decent.","Neutral"),
("Peaceful environment for study.","Positive"),
("Bathrooms need improvement.","Negative"),
("Good value for money.","Positive")
]
rid=1
for _,r in allh.iterrows():
    for _ in range(random.randint(6,10)):
        t,s=random.choice(texts)
        reviews.append([rid,r["id"],t,s,round(random.uniform(3,5),1)])
        rid+=1
pd.DataFrame(reviews,columns=["review_id","hostel_id","review_text","sentiment","rating"]).to_csv("reviews_final.csv",index=False)
print("Done")
