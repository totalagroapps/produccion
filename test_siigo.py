import requests
import time

# 1️⃣ AUTENTICACIÓN
auth = requests.post(
    "https://api.siigo.com/auth",
    json={
        "username": "Agroindustriagams@gmail.com",
        "access_key": "NTBmMGE4MDctMmZlMC00NGE0LTg1MjgtNmM1N2QyNDJmOTQzOm44ezJGWF9hTU0="
    }
)

print("AUTH STATUS:", auth.status_code)

token = auth.json()["access_token"]

time.sleep(2)  # evitar rate limit

# 2️⃣ PROBAR PRODUCTOS
headers = {
    "Authorization": f"Bearer {token}",
    "Partner-Id": "574c1a983f494df1b47a48c9c3a012cb",
    "Content-Type": "application/json"
}

test = requests.get(
    "https://api.siigo.com/v1/products",
    headers=headers
)

print("PRODUCT STATUS:", test.status_code)
print(test.text)