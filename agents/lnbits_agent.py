import requests

class LNbitsAgent:
    def __init__(self, name, lnbits_url, admin_key):
            self.name = name
                    self.url = lnbits_url.rstrip("/")
                            self.headers = {
                                            "X-Api-Key": admin_key,
                                                        "Content-type": "application/json"
                                                                }

                                                                    def get_balance(self):
                                                                            r = requests.get(f"{self.url}/api/v1/wallet", headers=self.headers)
                                                                                    if r.ok:
                                                                                                return r.json()["balance"]
                                                                                                        else:
                                                                                                                    raise Exception(f"Error: {r.status_code}, {r.text}")

                                                                                                                        def create_invoice(self, amount, memo="LNbitsAgent Invoice"):
                                                                                                                                payload = {
                                                                                                                                                "out": False,
                                                                                                                                                            "amount": amount,
                                                                                                                                                                        "memo": memo
                                                                                                                                                                                }
                                                                                                                                                                                        r = requests.post(f"{self.url}/api/v1/payments", headers=self.headers, json=payload)
                                                                                                                                                                                                if r.ok:
                                                                                                                                                                                                            return r.json()["payment_request"]
                                                                                                                                                                                                                    else:
                                                                                                                                                                                                                                raise Exception(f"Error: {r.status_code}, {r.text}")

                                                                                                                                                                                                                                    def pay_invoice(self, invoice):
                                                                                                                                                                                                                                            payload = {"out": True, "bolt11": invoice}
                                                                                                                                                                                                                                                    r = requests.post(f"{self.url}/api/v1/payments", headers=self.headers, json=payload)
                                                                                                                                                                                                                                                            if r.ok:
                                                                                                                                                                                                                                                                        return r.json()
                                                                                                                                                                                                                                                                                else:
                                                                                                                                                                                                                                                                                            raise Exception(f"Error: {r.status_code}, {r.text}")")")
                                                                                                                                }")
                            }
