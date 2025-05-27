import os
from src.agents.service_agent import ServiceAgent

class DataBot(ServiceAgent):
    def __init__(self, name="DataBot", description="Sells traffic data", price_sat=5000):
        super().__init__(name, description, price_sat)

    def serve_data(self, token, file_path="data/sample_dataset.json"):
        if self.accept_ecash_token(token):
            try:
                with open(file_path, "r") as f:
                    data = f.read()
                print(f"📡 {self.name} delivered the dataset.")
                return data
            except FileNotFoundError:
                print(f"❌ Data file not found: {file_path}")
        else:
            print(f"❌ Token was not accepted. Data not served.")
        return None
