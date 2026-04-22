import sys
sys.path.insert(0, "./src")

from identity.did import DIDIdentity

did = DIDIdentity()
print(did)
