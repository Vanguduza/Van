# Nissan GTR hosted — SECURITY DEFINER and public API privilege review

**Source:** authenticated Supabase project `bicyjghgdnzlnjqxzoud`, read-only PostgreSQL catalog inspection, 9 November 2026. **Disposition: REVIEW REQUIRED**, not a proven exploit or permission-change authorization.

## Findings

The live `public` schema contains **541 SECURITY DEFINER functions**, of which **22 are executable by the `anon` role**. All 22 have an explicit `anon` EXECUTE grant in `pg_proc.proacl`; three also have an EXECUTE grant to `PUBLIC`. None of the 22 relies on an absent/default ACL. The owner for all 22 is `postgres`.

The 22 function identities, without source bodies or customer data:

- Storage policy helpers: `_can_access_petty_cash_receipt_object(text)`, `_can_select_delivery_pod_object(text)`, `_can_select_review_photo_object(text)`, `_can_write_delivery_pod_object(text)`, `_can_write_product_image_object(text)`, `_can_write_review_photo_object(text)`
- Auth/customer/staff lookups: `_current_customer_id()`, `current_supplier_id()`, `has_staff_role(staff_role[])`, `is_pos_approver()`, `is_staff()`, `resolve_staff_login_email(text)`, `staff_login_is_locked(text)`, `_can_select_chat_thread(chat_threads)`
- Public-facing and pricing functions: `catalog_commerce_stock_for_oems(text[])`, `convert_to_base_uom(uuid,uuid,numeric)`, `get_delivery_track_point(uuid,text)`, `get_product_review_stats(uuid,text)`, `get_zig_exchange_rate(date)`, `list_customer_vehicle_master(text,integer,integer)`, `list_storefront_home_rails(integer)`, `resolve_item_price(uuid,uuid)`

The three functions with both explicit `anon` and `PUBLIC` execution grants are `catalog_commerce_stock_for_oems`, `has_staff_role` and `is_staff`. The others have explicit `anon` grants but not `PUBLIC`.

The public schema has **210 tables**, all RLS-enabled; 129 public tables have an `anon` SELECT grant, and there are two `anon`-targeted RLS policies with a literal-true USING expression. This does **not** imply unauthorized data access: RLS, actual policy roles, table grants, function validation and exposed API schemas must be considered together. The 28 informational no-policy lints also require case-by-case review.

## Review plan — no automatic privilege changes

1. Compare each function's actual body hash, security context, search path, authentication checks and execution ACL against the **post-forward** ARM64 final-state source contract, not the older pre-forward baseline.
2. Classify intended public endpoints separately from policy helpers, login lookup utilities and privileged staff/payment functions. Confirm that `auth.uid()` and role/ownership validation are applied wherever appropriate.
3. Determine which functions are reachable through the hosted Data API versus callable only inside policies or via privileged backend services. An `anon` EXECUTE grant alone does not prove a public REST endpoint is enabled.
4. For `SECURITY DEFINER`, review definer role, untrusted argument handling, search path, access to private tables, and potential data leaks without invoking effectful functions or changing production ACLs.
5. Require explicit application-owner review and migration test gates before any REVOKE/GRANT, RLS rewrite or API change. Do not break customer login, public product catalog, delivery token lookup or Storage policies by blanket revocation.

**Release status:** The 13-migration ARM64 native replay is independently tested, but its final post-forward function/policy/ACL contract has not been retained. No new target-native replay was executed during this review. Existing hosted users, data, permissions, scheduled jobs and the one-installation DIAL production environment remain unchanged. The earlier safety-refused DIAL canary activation has not been retried or bypassed.
