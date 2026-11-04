# TEST HARNESS ONLY. Compile an exact upstream application module in memory
# changing only listener IP. This does not alter production or release files.
p = System.fetch_env!("DIAL_POOLER_FIXTURE_APPLICATION_SOURCE")
source = File.read!(p)
expected = "ab6cef910bcde9852e0a26481df40a31a453c48a1d02d1f71686fd86bde98d56"
if Base.encode16(:crypto.hash(:sha256, source),case: :lower) != expected, do: raise("EXACT_UPSTREAM_POOLER_APP_REQUIRED")
old = "socket_opts: [port: port, keepalive: true]"
if length(String.split(source,old)) != 2, do: raise("POOLER_LISTEN_CALLSITE_DRIFT")
replacement = String.replace(source,old,"socket_opts: [ip: {127, 0, 0, 1}, port: port, keepalive: true]")
Code.compile_string(replacement,p)
config = Application.fetch_env!(:supavisor,SupavisorWeb.Endpoint)
http = Keyword.put(Keyword.fetch!(config,:http),:ip,{127,0,0,1})
Application.put_env(:supavisor,SupavisorWeb.Endpoint,Keyword.put(config,:http,http))
{:ok,_} = Application.ensure_all_started(:supavisor)
Process.sleep(:infinity)
