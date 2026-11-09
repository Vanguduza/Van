"""Positive business RPCs in the original disconnected GTR replay fixture.

Commit overrides permit multi-request workflows ONLY inside the disposable DB.
No production connection, table grants, provider calls or credential export.
The caller destroys this database after the unchanged original smoke suites.
"""
import base64
import hashlib
import hmac
import json
import re
import subprocess
import time
import uuid


def run(pgid, sidecar, ids, secret, fixture_sql, report):
    def docker_info(identity):
        p = subprocess.run(['docker', 'inspect', identity], capture_output=True, text=True, check=True, timeout=10)
        return json.loads(p.stdout)[0]

    pg = docker_info(pgid)
    http = docker_info(sidecar)
    attempt = pg['Config']['Labels'].get('dial.gtr.schema-replay', '')
    if not (re.fullmatch(r'attempt-[a-f0-9]{10}', attempt)
            and pg['HostConfig']['NetworkMode'] == 'none'
            and pg['Image'] == 'sha256:f371b5f3f2ac0a05703f33d6e6134515fb2498cab708fb948a0aeb7481467c00'
            and pg['Config']['User'] == '100:101'
            and len(pg['Mounts']) == 1
            and pg['Mounts'][0]['Source'] == '/var/tmp/dial-gtr-replay-fsur_69c/' + attempt + '/data'
            and http['HostConfig']['NetworkMode'] == 'container:' + pgid
            and http['HostConfig']['PidMode'] == 'container:' + pgid
            and not http['HostConfig'].get('PortBindings')
            and http['Config']['Labels'].get('dial.gtr.http-replay') == attempt
            and 'PGRST_DB_TX_END=rollback-allow-override' in http['Config']['Env']):
        raise RuntimeError('BUSINESS_FIXTURE_BOUNDARY_REFUSED')

    ids = dict(ids)
    ids['cashier'] = 'a0000000-0000-4000-8000-000000000004'
    now = int(time.time())
    checks = []

    def check(label, condition):
        checks.append({'label': label, 'passed': bool(condition)})
        print('BUSINESS_INVARIANT ' + label + ' ' + str(bool(condition)), flush=True)
        if not condition:
            raise RuntimeError('BUSINESS_INVARIANT_FAILED_' + label)

    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj, separators=(',', ':')).encode()).rstrip(b'=').decode()

    def token(actor):
        msg = enc({'alg': 'HS256', 'typ': 'JWT'}) + '.' + enc({
            'role': 'authenticated', 'sub': ids[actor], 'aud': 'authenticated', 'iat': now, 'exp': now + 600})
        return msg + '.' + base64.urlsafe_b64encode(hmac.new(secret.encode(), msg.encode(), 'sha256').digest()).rstrip(b'=').decode()

    requests = []

    def call(label, actor, rpc, body, expected=200, sqlstate=None):
        if actor not in ids or not re.fullmatch('[a-z][a-z0-9_]*', rpc):
            raise RuntimeError('BUSINESS_ENDPOINT_REFUSED')
        # Token and response never enter retained logs or files. CURL gets the
        # random fixture JWT via stdin rather than host process arguments.
        config = 'header = "Authorization: Bearer ' + token(actor) + '"\n'
        cmd = ['docker', 'exec', '-i', '--user', '100:101', pgid, 'curl', '--config', '-',
               '--silent', '--show-error', '--max-time', '10', '--connect-timeout', '2',
               '-D', '/tmp/business-http-headers', '-o', '-', '-w', '\n__STATUS__%{http_code}',
               '-X', 'POST', '-H', 'Content-Type: application/json', '-H', 'Prefer: tx=commit',
               '--data', json.dumps(body, separators=(',', ':')), 'http://127.0.0.1:3199/rpc/' + rpc]
        p = subprocess.run(cmd, input=config, capture_output=True, text=True, timeout=14)
        raw, marker, status = p.stdout.rpartition('\n__STATUS__')
        if p.returncode or not marker or len(raw) > 32768 or not status.isdigit():
            raise RuntimeError('BUSINESS_HTTP_MALFORMED_' + label)
        status = int(status)
        value = json.loads(raw)
        code = value.get('code') if isinstance(value, dict) else None
        headers = subprocess.run(['docker', 'exec', '--user', '100:101', pgid,
                                  'cat', '/tmp/business-http-headers'], capture_output=True, text=True, check=True, timeout=8).stdout
        committed = bool(re.search(r'(?im)^preference-applied:.*\btx=commit\b', headers))
        requests.append({'label': label, 'actor': actor, 'rpc': rpc, 'status': status,
                         'sqlstate': code, 'commit_preference_applied': committed,
                         'body_or_token_retained': False})
        print('BUSINESS_HTTP ' + label + ' ' + str(status) + ' CODE_' + str(code), flush=True)
        if status != expected or (sqlstate is not None and code != sqlstate):
            raise RuntimeError('BUSINESS_HTTP_FAILED_' + label + '_' + str(status) + '_' + str(code))
        if expected == 200 and not committed:
            raise RuntimeError('BUSINESS_COMMIT_NOT_ACKNOWLEDGED_' + label)
        return value

    def scalar(sql):
        return fixture_sql(sql).strip()

    def ident(value):
        return str(uuid.UUID(value))

    # Freeze effective authenticated INSERT/UPDATE/DELETE rights before setup.
    acl_sql = """SELECT md5(string_agg(c.oid::text||p.priv||has_table_privilege('authenticated',c.oid,p.priv)::text,',' ORDER BY c.oid,p.priv))
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN (VALUES('INSERT'),('UPDATE'),('DELETE')) p(priv)
WHERE n.nspname='public' AND c.relkind IN ('r','p');"""
    before_acl = scalar(acl_sql)
    setup = """BEGIN; SET LOCAL search_path=public,extensions;
DO $guard$ BEGIN
IF current_database()<>'gtr_replay' OR current_user<>'postgres'
THEN RAISE EXCEPTION 'BUSINESS_SETUP_NOT_FIXTURE'; END IF; END $guard$;
INSERT INTO auth.users(id,email) VALUES
('a0000000-0000-4000-8000-000000000004','http-cashier@synthetic.invalid');
INSERT INTO public.profiles(id) VALUES ('a0000000-0000-4000-8000-000000000004') ON CONFLICT DO NOTHING;
INSERT INTO public.staff_roles(user_id,role) VALUES('a0000000-0000-4000-8000-000000000004','sales');
INSERT INTO public.stock_items(oem_part_number,description,base_uom_id)
SELECT 'HTTP-BUSINESS-LOCAL-ONLY','Synthetic HTTP brake pad',id FROM public.uoms WHERE code='EA';
INSERT INTO public.price_list_items(price_list_id,stock_item_id,unit_price,core_charge)
SELECT p.id,s.id,48.25,0 FROM public.price_lists p, public.stock_items s
WHERE p.code='RETAIL' AND s.oem_part_number='HTTP-BUSINESS-LOCAL-ONLY';
SELECT public.post_stock_receipt(w.id,'Synthetic HTTP stock',jsonb_build_array(jsonb_build_object(
'stock_item_id',s.id,'uom_id',s.base_uom_id,'qty',10,'unit_cost',20,'currency','USD','valuation_method','FIFO')))
FROM public.warehouses w,public.stock_items s WHERE w.code='MAIN' AND s.oem_part_number='HTTP-BUSINESS-LOCAL-ONLY';
COMMIT;"""
    fixture_sql(setup)
    context = json.loads(scalar("""SELECT json_build_object('warehouse',w.id,'item',s.id,'uom',s.base_uom_id,
'grade',(SELECT id FROM public.hr_grades WHERE is_active ORDER BY code LIMIT 1))
FROM public.warehouses w,public.stock_items s WHERE w.code='MAIN' AND s.oem_part_number='HTTP-BUSINESS-LOCAL-ONLY';"""))
    warehouse, item, uom, grade = (ident(context[k]) for k in ('warehouse', 'item', 'uom', 'grade'))

    # HR's admitted RPC succeeds with the original table-level INSERT denied.
    check('hr_direct_insert_still_denied', scalar("SELECT NOT has_table_privilege('authenticated','public.hr_roles','INSERT');") == 't')
    hr = ident(call('admin_create_hr_role', 'admin', 'create_hr_role', {'p_title': 'Synthetic HTTP role', 'p_grade_id': grade}))
    check('hr_role_persisted_in_fixture', scalar("SELECT count(*) FROM public.hr_roles WHERE id='" + hr + "' AND created_by='" + ids['admin'] + "';") == '1')
    call('customer_cannot_create_hr_role', 'customer_a', 'create_hr_role', {'p_title': 'Forbidden synthetic role', 'p_grade_id': grade}, 400, 'P0001')

    # Customer creates and updates a garage entry; another customer is denied.
    garage = ident(call('customer_create_garage', 'customer_a', 'upsert_customer_garage_vehicle', {
        'p_make': 'Nissan', 'p_model': 'Navara', 'p_chassis_code': 'D40', 'p_model_slug': 'navara-d40',
        'p_vehicle_master_id': 'published:navara/d40', 'p_is_primary': True}))
    check('garage_owned_by_customer', scalar("SELECT count(*) FROM public.customer_garage_vehicles g JOIN public.customers c ON c.id=g.customer_id WHERE g.id='" + garage + "' AND c.profile_id='" + ids['customer_a'] + "';") == '1')
    call('customer_partial_garage_update', 'customer_a', 'upsert_customer_garage_vehicle', {'p_id': garage, 'p_vehicle_master_id': 'published:updated'})
    call('peer_cannot_update_garage', 'customer_b', 'upsert_customer_garage_vehicle', {'p_id': garage, 'p_vehicle_master_id': 'peer-overwrite'}, 400, 'P0001')
    check('garage_identity_preserved', scalar("SELECT count(*) FROM public.customer_garage_vehicles WHERE id='" + garage + "' AND chassis_code='D40' AND model_slug='navara-d40' AND vehicle_master_id='published:updated';") == '1')

    # Merchandising uses its existing definer RPC, without granting direct DML.
    check('merchandise_rpc_returns_item', call('admin_update_merchandise', 'admin', 'upsert_staff_product_page', {'p_stock_item_id': item, 'p_unit_price': 48.25}) == item)
    call('customer_cannot_update_merchandise', 'customer_a', 'upsert_staff_product_page', {'p_stock_item_id': item, 'p_unit_price': 1}, 400, 'P0001')
    check('price_unchanged_after_denial', scalar("SELECT count(*) FROM public.price_list_items WHERE stock_item_id='" + item + "' AND unit_price=48.25;") == '1')

    # Positive real web/tablet call shapes, with a sales-only cashier JWT.
    cart = ident(call('cashier_create_cart', 'cashier', 'create_pos_cart', {'p_warehouse_id': warehouse, 'p_currency': 'USD', 'p_fulfillment_mode': 'immediate'}))
    call('customer_cannot_add_cart_line', 'customer_a', 'add_cart_line', {'p_cart_id': cart, 'p_stock_item_id': item, 'p_uom_id': uom, 'p_qty': 3}, 400, 'P0001')
    call('cashier_add_cart_line', 'cashier', 'add_cart_line', {'p_cart_id': cart, 'p_stock_item_id': item, 'p_uom_id': uom, 'p_qty': 3})
    check('cart_total_144_75', scalar("SELECT sum(line_total)=144.75 FROM public.pos_cart_lines WHERE cart_id='" + cart + "';") == 't')
    vehicle = json.loads(scalar("""SELECT json_build_object('p_model_slug',btrim(regexp_replace(lower(btrim(model)),'[^a-z0-9]+','-','g'),'-'),
'p_model_name',model,'p_generation',chassis_code,'p_chassis_code',chassis_code,'p_engine_code',engine_code)
FROM public.catalog_r2_vehicle_master WHERE maker_slug='nissan' ORDER BY r2_scope_key LIMIT 1;"""))
    call('cashier_set_published_vehicle', 'cashier', 'set_pos_cart_vehicle', {'p_cart_id': cart, **vehicle})
    call('reject_unpublished_vehicle', 'cashier', 'set_pos_cart_vehicle', {'p_cart_id': cart, 'p_model_slug': 'not-published', 'p_model_name': 'Unknown', 'p_generation': 'FAKE', 'p_chassis_code': 'FAKE', 'p_engine_code': 'FAKE'}, 400, 'P0001')
    call('cashier_park_cart', 'cashier', 'park_pos_cart', {'p_cart_id': cart})
    call('cashier_resume_cart', 'cashier', 'resume_pos_cart', {'p_cart_id': cart})
    till = ident(call('cashier_open_till', 'cashier', 'open_pos_till_session', {'p_warehouse_id': warehouse, 'p_device_id': 'synthetic-http-tablet', 'p_opening_float': 0, 'p_currency': 'USD'}))
    call('cashier_attach_till', 'cashier', 'attach_pos_cart_till_session', {'p_cart_id': cart, 'p_session_id': till})
    checkout_request = str(uuid.uuid4())
    checkout_body = {'p_cart_id': cart, 'p_checkout_request_id': checkout_request, 'p_reservation_ttl': '20 minutes'}
    order = ident(call('cashier_reserve_checkout', 'cashier', 'prepare_pos_commerce_checkout_v2', checkout_body))
    check('checkout_retry_same_order', call('checkout_idempotent_retry', 'cashier', 'prepare_pos_commerce_checkout_v2', checkout_body) == order)
    check('unpaid_order_has_no_invoice', scalar("SELECT sales_invoice_id IS NULL FROM public.commerce_orders WHERE id='" + order + "';") == 't')
    for label, tenders in [('reject_overtender', [{'tender': 'cash', 'amount': 200}]), ('reject_unverified_digital_tender', [{'tender': 'ecocash', 'amount': 144.75}])]:
        call(label, 'cashier', 'settle_pos_commerce_tenders', {'p_order_id': order, 'p_payment_request_id': str(uuid.uuid4()), 'p_tenders': tenders}, 400, 'P0001')
    settle_body = {'p_order_id': order, 'p_payment_request_id': str(uuid.uuid4()), 'p_tenders': [{'tender': 'cash', 'amount': 100}, {'tender': 'bank', 'amount': 44.75}]}
    settled = call('cashier_split_settlement', 'cashier', 'settle_pos_commerce_tenders', settle_body)
    invoice = ident(settled['invoice_id'])
    check('two_tender_legs', len(settled['payment_entry_ids']) == 2)
    repeated = call('settlement_idempotent_retry', 'cashier', 'settle_pos_commerce_tenders', settle_body)
    check('settlement_retry_same_invoice', repeated['invoice_id'] == invoice)
    check('settlement_retry_same_payment_entries', repeated['payment_entry_ids'] == settled['payment_entry_ids'])
    check('invoice_posted_once', scalar("SELECT count(*) FROM public.sales_invoices WHERE id='" + invoice + "' AND status='posted';") == '1')
    check('three_stock_units_issued_once', scalar("SELECT coalesce(sum(quantity),0)=7 FROM public.stock_levels WHERE stock_item_id='" + item + "' AND warehouse_id='" + warehouse + "';") == 't')
    check('all_journals_balanced', scalar('SELECT NOT EXISTS(SELECT journal_entry_id FROM public.journal_entry_lines GROUP BY journal_entry_id HAVING sum(debit)<>sum(credit));') == 't')
    call('cashier_direct_journal_denied', 'cashier', 'post_journal_entry', {'p_entry_date': time.strftime('%Y-%m-%d', time.gmtime()), 'p_description': 'Forbidden direct post', 'p_currency': 'USD', 'p_exchange_rate': 1, 'p_lines': [{'account_code': '1000', 'debit': 1, 'credit': 0}, {'account_code': '4000', 'debit': 0, 'credit': 1}]}, 400, 'P0001')
    check('authenticated_dml_privileges_unchanged', scalar(acl_sql) == before_acl)
    report['business_http'] = {'scope': 'DISPOSABLE_NETWORK_NONE_SYNTHETIC_ONLY', 'requests': requests,
                               'invariants': checks, 'success': True, 'production_writes': False,
                               'application_grants_changed': False, 'external_provider_calls': False,
                               'fixture_commit_overrides_used': True, 'real_auth_login_tested': False}
