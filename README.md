



cd /Users/dm/code/agent/operation-agent
source ./activate
hermes gateway run -v

cd /Users/dm/code/agent/operation-agent
nvm use 22
npm ci

HERMES_DESKTOP_HERMES_ROOT="$PWD" npm run dev --workspace apps/desktop