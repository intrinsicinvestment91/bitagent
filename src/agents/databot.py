from src.agents.base_agent import BaseAgent

class DataBot(BaseAgent):
    def __init__(self):
        super().__init__(name="DataBot", role="data_broker")
        self.price_sat = 5000

    def serve_data(self, token: dict, file_path: str = "data/sample_dataset.json"):
        if self.wallet.accept_token(token, required_amount=self.price_sat):
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
