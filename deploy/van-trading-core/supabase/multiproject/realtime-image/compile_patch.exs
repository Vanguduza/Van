# Derivative image build only. No application start, database, network or Owner effect.
source = "/tmp/dial-replication-connection.ex"
beam = "/app/lib/realtime-2.152.0/ebin/Elixir.Realtime.Tenants.ReplicationConnection.beam"
digest = fn path -> :crypto.hash(:sha256, File.read!(path)) |> Base.encode16(case: :lower) end
expected_source = "246686ac944ac3a342d34527d0de38e2b2bdce290bbe2156ade23e898025c81d"
expected_original = "e4d17b486b922c88add7ffec8390d16027d3d9cbeaa58bedbee7be33256b5f08"
if digest.(source) != expected_source, do: raise("DIAL_REALTIME_PATCH_SOURCE_MISMATCH")
if digest.(beam) != expected_original, do: raise("DIAL_REALTIME_BASE_MODULE_MISMATCH")
[{Realtime.Tenants.ReplicationConnection, bytes}] = Code.compile_file(source)
File.write!(beam, bytes)
for {tenant, expected} <- [
  {"fixture", "dial_rt_messages_ad6eab021a76630d9d84940b65d672238d19e2ed"},
  {"nissan", "dial_rt_messages_41f370b64233f0e0d64ebcaf957b10783eadcc44"}
] do
  actual = Realtime.Tenants.ReplicationConnection.replication_slot_name("realtime", "messages", tenant)
  if actual != expected, do: raise("DIAL_REALTIME_SLOT_SCOPE_SELF_CHECK_FAILED")
end
receipt = %{
  kind: "DIAL_REALTIME_IMAGE_PATCH_BUILD_NOT_QUALIFICATION",
  upstream_version: "2.152.0",
  upstream_commit: "c8b27c7a37a5c60fee5b5a11632231d8e2c0a8c9",
  patched_source_sha256: expected_source,
  original_module_sha256: expected_original,
  resulting_module_sha256: digest.(beam),
  elixir: System.version(),
  otp: System.otp_release(),
  production_qualified: false
}
File.write!("/app/dial-realtime-slot-patch.json", Jason.encode!(receipt))
IO.puts("DIAL_REALTIME_SLOT_PATCH_BUILD_COMPLETE_NOT_QUALIFIED")
