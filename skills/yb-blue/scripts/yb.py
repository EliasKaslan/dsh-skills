"""Retired unsafe/stale executable. Original is preserved in the external review backup."""
import sys
sys.stderr.write('DSH_HELPER_RETIRED: unsafe remote client retired: cross-origin auth and unchecked outbound attachments; use reviewed current bridge API. No credential/config/network action was performed.\n')
raise SystemExit(78)
