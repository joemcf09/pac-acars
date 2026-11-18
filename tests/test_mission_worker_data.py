import json

import mission_worker


def test_mission_worker_uses_shared_data_for_status(monkeypatch, tmp_path):
    monkeypatch.setenv('PAC_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(mission_worker, '_run_once', lambda: True)

    assert mission_worker.worker_data_dir() == tmp_path
    assert mission_worker.run_once() is True
    status = json.loads((tmp_path / 'mission-worker-status.json').read_text())
    assert status['state'] == 'success'
