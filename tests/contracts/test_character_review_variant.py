"""Approved review build preparation with real packaged sources, isolated output fixtures.

These tests do not stage accepted production assets or grant any owner/artwork pass.
"""
from pathlib import Path
import importlib.util,json,hashlib,shutil,tempfile,unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('character_review_build',ROOT/'android/tools/prepare_character_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ReviewVariantPreparation(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        files=['android/character-review/REVIEW_REQUEST.json','docs/rebuild/rev118/character-review/OWNER_INSTRUCTION.json','docs/rebuild/rev118/character-review/SOURCE_INVENTORY.json','docs/rebuild/rev118/floating-hardening/RIVE_AUTHORING_AND_PACKAGING_REVIEW_20261105.zip','docs/rebuild/rev118/receipts/floating-20261105-pinned-native-core/SUMMARY.json','android/app/src/main/java/com/dial/van/visual/VanContextGesture.kt','android/app/build.gradle.kts','visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png']
        for name in files:
            dest=self.root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        self.output=self.root/module.OUTPUT
        self.provenance=self.root/'android/app/build/generated/van-build-provenance/van-build-provenance.json';self.provenance.parent.mkdir(parents=True)
        self.provenance.write_text(json.dumps({'source_sha':'1'*40,'application_id':'com.dial.van'}))
    def prepare(self):return module.prepare(self.root,self.output,self.provenance)
    def alter(self,path,key,value):
        p=self.root/path;x=json.loads(p.read_text());x[key]=value;p.write_text(json.dumps(x))
    def test_actual_locked_candidate_is_packaged_only_in_generated_review_path(self):
        r=self.prepare();self.assertEqual('UNACCEPTED_CHARACTER_REVIEW_PACKAGE_VERIFIED',r['status'])
        self.assertEqual('a5b848a02887de309d2ee4db2dbc167efaeb123ca0078278155c8b7b4bb8f5dc',module.sha(self.output/'van_review.riv'))
        self.assertFalse(r['production_accepted']);self.assertFalse(r['physical_accepted'])
        self.assertFalse((self.root/'android/app/src/main/assets/van.riv').exists())
    def test_other_output_paths_never_receive_the_review_payload(self):
        for path in ['android/app/src/main/assets','android/app/src/debug/assets','android/app/src/release/assets']:
            with self.subTest(path=path),self.assertRaises(ValueError):module.prepare(self.root,self.root/path,self.provenance)
            self.assertFalse((self.root/path).exists())
    def test_review_marker_and_provenance_name_the_separate_app(self):
        self.prepare();m=json.loads((self.output/'van-character-review.json').read_text());p=json.loads((self.output/'van-build-provenance.json').read_text())
        self.assertEqual('com.dial.van.characterreview',m['application_id']);self.assertEqual(m['source_commit'],p['source_sha']);self.assertTrue(p['review_only'])
    def test_review_cannot_intercept_the_production_deep_link_scheme(self):
        source=(ROOT/'android/app/src/characterReview/AndroidManifest.xml').read_text()
        self.assertIn('tools:node="replace"',source);self.assertIn('android.intent.action.MAIN',source)
        self.assertNotIn('android:scheme="van"',source)
        self.assertIn('android:permission="android.permission.DUMP"',source)
    def test_approved_payload_scope_is_exact_not_a_general_rig_switch(self):
        a=self.root/'docs/rebuild/rev118/character-review/OWNER_INSTRUCTION.json';x=json.loads(a.read_text());x['exact_candidate_scope']['rive_sha256']='0'*64;a.write_text(json.dumps(x))
        q=self.root/module.REQUEST;r=json.loads(q.read_text());r['owner_instruction_sha256']=module.sha(a);q.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'approved candidate scope'):self.prepare()

    def test_request_cannot_declare_production_or_physical_acceptance(self):
        for key in ['production_accepted','physical_accepted']:
            saved=(self.root/module.REQUEST).read_bytes();self.alter(module.REQUEST,key,True)
            with self.assertRaises(ValueError):self.prepare()
            (self.root/module.REQUEST).write_bytes(saved)
    def test_owner_instruction_change_is_refused(self):
        self.alter('docs/rebuild/rev118/character-review/OWNER_INSTRUCTION.json','owner_response','No')
        with self.assertRaisesRegex(ValueError,'instruction changed'):self.prepare()
    def test_inventory_cannot_issue_independent_or_owner_acceptance(self):
        self.alter('docs/rebuild/rev118/character-review/SOURCE_INVENTORY.json','source_owner_accepted_complete',True)
        with self.assertRaisesRegex(ValueError,'Inventory cannot'):self.prepare()
    def test_runtime_change_refused_instead_of_switching_native_version(self):
        p=self.root/'android/app/build.gradle.kts';p.write_text(p.read_text().replace('rive-android:9.13.10','rive-android:9.6.5'))
        with self.assertRaisesRegex(ValueError,'Runtime changed'):self.prepare()
    def test_source_archive_corruption_is_rejected(self):
        p=self.root/'docs/rebuild/rev118/floating-hardening/RIVE_AUTHORING_AND_PACKAGING_REVIEW_20261105.zip';p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'archive changed'):self.prepare()
    def test_adopted_master_is_checked_not_invented_from_source_complete_flag(self):
        p=self.root/'visual-authority/character-forge/01-master-candidates/van_master_source_candidate_b.png';p.write_bytes(p.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError,'Candidate B identity'):self.prepare()
    def test_native_evidence_cannot_be_replaced_by_an_unrelated_pass(self):
        self.alter('docs/rebuild/rev118/receipts/floating-20261105-pinned-native-core/SUMMARY.json','candidate_binary_sha256','0'*64)
        with self.assertRaisesRegex(ValueError,'evidence changed'):self.prepare()
    def test_build_provenance_is_not_an_arbitrary_supplied_json(self):
        wrong=self.root/'wrong.json';wrong.write_bytes(self.provenance.read_bytes())
        with self.assertRaisesRegex(ValueError,'actual generated'):module.prepare(self.root,self.output,wrong)
    def test_default_debug_release_and_unknown_variants_reject_review_payload(self):
        self.prepare()
        for variant in ['debug','release','unknown','characterreview']:
            with self.subTest(variant=variant),self.assertRaisesRegex(ValueError,'NONREVIEW'):module.guard(self.root,variant,self.output)
    def test_renamed_rive_cannot_hide_in_release_assets(self):
        clean=self.root/'merged-release';clean.mkdir();self.prepare();shutil.copyfile(self.output/'van_review.riv',clean/'renamed.riv')
        with self.assertRaisesRegex(ValueError,'NONREVIEW'):module.guard(self.root,'release',clean)
    def test_empty_regular_asset_set_remains_accepted_without_review(self):
        clean=self.root/'normal-assets';clean.mkdir();(clean/'ordinary.json').write_text('{}')
        self.assertEqual('NO_REVIEW_ASSETS',module.guard(self.root,'debug',clean)['status'])
    def test_exact_copy_tamper_is_detected_after_merge(self):
        self.prepare();p=self.output/'van_review.riv';p.write_bytes(p.read_bytes()+b'bad')
        with self.assertRaisesRegex(ValueError,'payload changed'):module.guard(self.root,'characterReview',self.output)
    def test_accepted_and_unaccepted_asset_names_cannot_mix(self):
        self.prepare();(self.output/'van.riv').write_bytes(b'other')
        with self.assertRaisesRegex(ValueError,'must not be mixed'):module.guard(self.root,'characterReview',self.output)
    def test_marker_false_acceptance_flags_are_rechecked_at_packaging(self):
        self.prepare();self.alter(module.OUTPUT+'/van-character-review.json','production_accepted',True)
        with self.assertRaisesRegex(ValueError,'self-accept'):module.guard(self.root,'characterReview',self.output)
    def test_manifest_does_not_accept_an_old_build_sha(self):
        self.prepare();self.alter(module.OUTPUT+'/van-build-provenance.json','source_sha','2'*40)
        with self.assertRaisesRegex(ValueError,'provenance mismatch'):module.guard(self.root,'characterReview',self.output)
    def test_repeat_preparation_revalidates_and_preserves_exact_identity(self):
        self.prepare();old=(self.output/'van-character-review.json').read_bytes();self.prepare();self.assertEqual(old,(self.output/'van-character-review.json').read_bytes())
    def test_symlinked_review_output_cannot_escape(self):
        other=self.root/'somewhere';other.mkdir();self.output.parent.mkdir(parents=True,exist_ok=True);self.output.symlink_to(other,target_is_directory=True)
        with self.assertRaises(ValueError):self.prepare()
    def test_unexpected_output_is_preserved_not_deleted(self):
        self.output.mkdir(parents=True);extra=self.output/'owner-data';extra.write_text('keep')
        with self.assertRaisesRegex(ValueError,'Unexpected review output'):self.prepare()
        self.assertEqual('keep',extra.read_text())
    def test_gradle_creates_only_separate_debuggable_variant_and_guarded_packages(self):
        s=(ROOT/'android/app/build.gradle.kts').read_text()
        for token in ['create("characterReview")','isDebuggable = true','applicationIdSuffix = ".characterreview"','assert${cap}CharacterAssetIsolation','dependsOn(inspect)','Character review and release may not share']:
            self.assertIn(token,s)
        self.assertNotIn('sourceSets.getByName("main").assets.srcDir(prepareCharacterReview',s)
    def test_real_floating_renderer_and_selector_share_one_review_asset_resolver(self):
        view=(ROOT/'android/app/src/main/java/com/dial/van/visual/VanRiveAvatar.kt').read_text()
        chooser=(ROOT/'android/app/src/main/java/com/dial/van/visual/VanCanvasFallback.kt').read_text()
        self.assertIn('VanCharacterAssets.load(ctx)',view);self.assertIn('VanCharacterAssets.load(context)',chooser)
    def test_review_notice_is_persistent_and_default_debug_flag_remains_false(self):
        for name in ['overlay/VanOverlayWorkboards.kt','overlay/OverlayPersonalControls.kt','command/CommandCentreActivity.kt']:
            self.assertIn('VanCharacterReviewNotice()',(ROOT/'android/app/src/main/java/com/dial/van'/name).read_text())
        s=(ROOT/'android/app/build.gradle.kts').read_text();self.assertIn('buildConfigField("boolean", "VAN_CHARACTER_REVIEW", "false")',s)
if __name__=='__main__':unittest.main(verbosity=2)
