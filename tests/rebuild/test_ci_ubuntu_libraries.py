"""The graphics prerequisite must retain signed Ubuntu security sources."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("ci_ubuntu_libraries",Path(__file__).resolve().parents[2]/"tools/rebuild/ci_ubuntu_libraries.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RELEASE = 'ID=ubuntu\nVERSION_CODENAME=noble\n'
SOURCES = 'Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\nSuites: noble noble-updates noble-backports\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n\nTypes: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\nSuites: noble-security\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'


def test_commands_select_existing_ubuntu_sources_for_both_update_and_install():
    update,install = module.commands(RELEASE,SOURCES)
    for command in (update,install):
        assert "Dir::Etc::sourcelist=/etc/apt/sources.list.d/ubuntu.sources" in command
        assert "Dir::Etc::sourceparts=-" in command
        assert "--allow-unauthenticated" not in command and "||" not in command
    assert update[-1] == "update"
    assert install[-len(module.LIBRARIES):] == list(module.LIBRARIES)


@pytest.mark.parametrize("release,sources", [(RELEASE,SOURCES.replace("noble-security","noble-updates")),
    (RELEASE,SOURCES.replace("Signed-By:","Removed-Signature:")),("ID=debian\nVERSION_CODENAME=trixie",SOURCES)])
def test_incomplete_security_or_signature_configuration_is_refused(release,sources):
    with pytest.raises(ValueError):module.commands(release,sources)


def test_installation_propagates_update_failure_without_attempting_install(monkeypatch):
    monkeypatch.setattr(module.Path,"read_text",lambda self:RELEASE if self.name=="os-release" else SOURCES)
    calls=[]
    def fail(command,**kwargs):
        calls.append(command)
        assert kwargs["check"] is True
        raise subprocess.CalledProcessError(100,command)
    monkeypatch.setattr(module.subprocess,"run",fail)
    with pytest.raises(subprocess.CalledProcessError):module.main()
    assert len(calls)==1 and calls[0][-1]=="update"


def test_comments_and_folded_suite_fields_preserve_source_selection():
    folded = "# runner-managed source file\n\n"+SOURCES.replace("Suites: noble-security", "Suites:\n noble-security")
    assert module.commands(RELEASE,folded) == module.commands(RELEASE,SOURCES)


def test_disabled_security_suite_does_not_satisfy_the_security_requirement():
    disabled = SOURCES.replace("Suites: noble-security", "Enabled: no\nSuites: noble-security")
    with pytest.raises(ValueError,match="security suites"):
        module.commands(RELEASE,disabled)
