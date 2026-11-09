# Gateway wire contracts

Inherits root and gateway/AGENTS.md. Keep canonical and auxiliary method catalogs distinct. Python schemas generate apps/shared/src/gateway-contract.generated.ts and gateway-contract.openrpc.json through scripts/gen_gateway_contracts.py. Internal path moves must not change method names, payload fields, event names, capability rules or stored session identities. Run tests/gateway/contracts and canonical contract tests through scripts/run_tests.sh.
