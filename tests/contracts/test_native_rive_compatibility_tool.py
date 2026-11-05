"""Negative provenance/output checks for the native tool, not simulated native passes.

The small fixture trees test rejection logic only. The separate recorded run uses
1,500 original files and executes the actual compiled character through C++.
"""
from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import tempfile
import unittest
from tools.rebuild.native_rive_compatibility import run as tool
from tools.rebuild.native_rive_compatibility import verify_result as verifier

class NativeSourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'core';(self.source/'src').mkdir(parents=True)
        (self.source/'include').mkdir();(self.source/'src/example.cpp').write_text('int original() { return 7; }\n')
        (self.source/'include/example.hpp').write_text('int original();\n')
        self.core=self.root/'core-tree.json';self.android=self.root/'android-tree.json';self.gradle=self.root/'build.gradle.kts'
        self.gradle.write_text('implementation("app.rive:rive-android:9.13.10")')
        self.ct={'sha':'fixture-core','truncated':False,'tree':[{'type':'blob','path':str(p.relative_to(self.source)),'sha':tool.git_blob(p.read_bytes())} for p in sorted(self.source.rglob('*')) if p.is_file()]}
        self.at={'sha':'fixture-android','truncated':False,'tree':[{'path':'submodules/rive-runtime','type':'commit','sha':'fixture-core'}]}
        self.lock={'core_commit':'fixture-core','android_commit':'fixture-android','android_version':'9.13.10','cpp_sources':1}
        self.write()
    def write(self):
        self.core.write_text(json.dumps(self.ct));self.android.write_text(json.dumps(self.at))
        self.lock['core_tree_response_sha256']=tool.sha(self.core);self.lock['android_tree_response_sha256']=tool.sha(self.android)
    def verify(self):return tool.verify_inputs(self.source,self.core,self.android,self.gradle,self.lock)
    def test_known_git_blob_encoding(self):
        self.assertEqual('e69de29bb2d1d6434b8b29ae775ad8c2e48c5391',tool.git_blob(b''))
    def test_exact_fixture_sources_and_android_binding_are_checkable(self):
        result=self.verify();self.assertEqual(2,result['source_files']);self.assertEqual(1,result['cpp_sources'])
        self.assertEqual(tool.sha(self.gradle),result['gradle_sha256'])
    def test_wrong_android_dependency_does_not_repin_the_application(self):
        self.gradle.write_text('implementation("app.rive:rive-android:9.6.5")');before=self.gradle.read_bytes()
        with self.assertRaisesRegex(ValueError,'runtime pin differs'):self.verify()
        self.assertEqual(before,self.gradle.read_bytes())
    def test_duplicate_declared_runtime_requires_review(self):
        self.gradle.write_text(self.gradle.read_text()+'\nimplementation("app.rive:rive-android:9.13.10")')
        with self.assertRaisesRegex(ValueError,'runtime pin differs'):self.verify()
    def test_modified_core_cpp_cannot_be_called_original(self):
        (self.source/'src/example.cpp').write_text('int original() { return 99; }')
        with self.assertRaisesRegex(ValueError,'Native source modified'):self.verify()
    def test_modified_header_is_rejected_too(self):
        (self.source/'include/example.hpp').write_text('int replacement();')
        with self.assertRaisesRegex(ValueError,'Native source modified'):self.verify()
    def test_additional_cpp_source_is_not_silently_compiled(self):
        (self.source/'src/extra.cpp').write_text('int extra;')
        with self.assertRaisesRegex(ValueError,'set differs'):self.verify()
    def test_deleted_original_cpp_cannot_make_a_smaller_fake_core(self):
        (self.source/'src/example.cpp').unlink()
        with self.assertRaisesRegex(ValueError,'set differs'):self.verify()
    def test_source_file_symlink_is_not_an_immutable_input(self):
        target=self.root/'elsewhere.cpp';target.write_text((self.source/'src/example.cpp').read_text())
        (self.source/'src/example.cpp').unlink();(self.source/'src/example.cpp').symlink_to(target)
        with self.assertRaisesRegex(ValueError,'symlink'):self.verify()
    def test_upstream_response_hash_is_checked_before_content(self):
        self.core.write_text(self.core.read_text()+' ')
        with self.assertRaisesRegex(ValueError,'reviewed lock'):self.verify()
    def test_truncated_source_tree_cannot_be_used_as_complete(self):
        self.ct['truncated']=True;self.write()
        with self.assertRaisesRegex(ValueError,'Incomplete'):self.verify()
    def test_android_submodule_binding_cannot_name_another_core(self):
        self.at['tree'][0]['sha']='different';self.write()
        with self.assertRaisesRegex(ValueError,'does not bind'):self.verify()
    def test_missing_or_duplicate_submodule_refused(self):
        for value in [[],[self.at['tree'][0]]*2]:
            self.at['tree']=value;self.write()
            with self.assertRaisesRegex(ValueError,'does not bind'):self.verify()
    def test_git_tag_identity_not_only_file_count_is_verified(self):
        self.ct['sha']='different';self.write()
        with self.assertRaisesRegex(ValueError,'Wrong native'):self.verify()
    def test_cpp_source_count_is_locked(self):
        self.lock['cpp_sources']=2
        with self.assertRaisesRegex(ValueError,'Incomplete native C'):self.verify()
    def test_cpp_driver_preserves_the_plus_plus_leaf_identity(self):
        compiler=self.root/'clang';compiler.write_text('fixture executable')
        alias=self.root/'clang++';alias.symlink_to(compiler)
        self.assertEqual('clang++',tool.cpp_driver(alias).name)
        self.assertEqual(alias,tool.cpp_driver(alias))
    def test_c_driver_is_rejected_before_expensive_build(self):
        compiler=self.root/'clang';compiler.write_text('fixture executable')
        with self.assertRaisesRegex(ValueError,'C\+\+ compiler'):tool.cpp_driver(compiler)

    def test_source_path_escape_and_absolute_paths_refused(self):
        for raw in ['../outside','/tmp/outside','src/../../outside']:
            with self.subTest(path=raw),self.assertRaises(ValueError):tool.source_path(self.source,raw)

class NativeOutputIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'.git').mkdir();(self.root/'evidence').mkdir();(self.root/'android').mkdir()
        patcher=patch.object(tool,'ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)
    def test_new_private_output_is_create_only(self):
        output=self.root/'.git/diagnostic';self.assertEqual(output,tool.new_output(output))
        with self.assertRaisesRegex(ValueError,'already exists'):tool.new_output(output)
    def test_android_assets_cannot_be_selected_as_diagnostic_output(self):
        with self.assertRaisesRegex(ValueError,'must stay'):tool.new_output(self.root/'android/promoted-assets')
        self.assertFalse((self.root/'android/promoted-assets').exists())
    def test_symlinked_parent_cannot_escape_repo(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root/'.git/escape').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):tool.new_output(self.root/'.git/escape/output')
            self.assertFalse((Path(outside)/'output').exists())
    def test_no_implicit_directory_creation_outside_declared_parent(self):
        with self.assertRaisesRegex(ValueError,'parent explicitly'):tool.new_output(self.root/'.git/missing/nested')
    def test_gate_and_acceptance_paths_are_not_output_targets(self):
        (self.root/'docs').mkdir()
        with self.assertRaisesRegex(ValueError,'must stay'):tool.new_output(self.root/'docs/character_forge')

class NativeTraceBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'runtime.jsonl').write_text('{"kind":"fixture-only"}\n');(self.root/'runtime.stderr').write_text('')
        self.row={'exit_code':0,'native_core_commit':verifier.EXPECTED_CORE,'stdout_sha256':verifier.sha(self.root/'runtime.jsonl'),'stderr_sha256':verifier.sha(self.root/'runtime.stderr')}
        self.write()
    def write(self):(self.root/'EXECUTION_RECEIPT.json').write_text(json.dumps(self.row))
    def test_trace_loading_is_not_itself_a_behavior_pass(self):
        values,_=verifier.load_trace(self.root);self.assertEqual('fixture-only',values[0]['kind'])
        self.assertNotIn('passed',values[0])
    def test_failed_native_exit_is_never_relabelled_green(self):
        self.row['exit_code']=1;self.write()
        with self.assertRaisesRegex(AssertionError,'did not succeed'):verifier.load_trace(self.root)
    def test_native_trace_modified_after_process_is_refused(self):
        (self.root/'runtime.jsonl').write_text('{"kind":"invented"}\n')
        with self.assertRaisesRegex(AssertionError,'trace changed'):verifier.load_trace(self.root)
    def test_even_hashed_native_warning_requires_review(self):
        (self.root/'runtime.stderr').write_text('PNG decode warning')
        self.row['stderr_sha256']=verifier.sha(self.root/'runtime.stderr');self.write()
        with self.assertRaisesRegex(AssertionError,'warning/error'):verifier.load_trace(self.root)
    def test_wrong_native_revision_is_not_the_pinned_android_core(self):
        self.row['native_core_commit']='unrelated';self.write()
        with self.assertRaisesRegex(AssertionError,'Wrong native core'):verifier.load_trace(self.root)
    def test_original_software_scope_explicitly_excludes_admission(self):
        source=Path(verifier.__file__).read_text()
        self.assertIn("'android_native_render_qualified':False",source)
        self.assertIn("'physical_tested':False",source);self.assertIn("'owner_accepted':False",source)
        runner=Path(tool.__file__).read_text()
        self.assertNotIn('cmd_rive_stage',runner);self.assertNotIn('cmd_integrate',runner)

if __name__=='__main__':unittest.main(verbosity=2)
