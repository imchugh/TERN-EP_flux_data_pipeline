"""
Tests for transfer_tasks path resolution.

Patches infrastructure.rclone_transfer.transfer so no data is moved;
asserts that each task resolves the correct src and dst before handing
off to rclone.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import tasks.transfer_tasks as tt

PATCH = 'infrastructure.rclone_transfer.transfer'
SITE = 'HowardSprings'


class TestPullTasks(unittest.TestCase):

    @patch(PATCH)
    def test_pull_profile_raw(self, mock_transfer):
        # pull_profile_raw is restricted to remote-collected sites.
        tt.pull_profile_raw('CumberlandPlain')
        mock_transfer.assert_called_once_with(
            src='uqrdm:TERNEP-Q5937/Sites/CumberlandPlain/Data/Profile/Raw',
            dst=Path('/store/Raw_data/CumberlandPlain/Profile'),
            )

    @patch(PATCH)
    def test_pull_profile_raw_rejects_non_remote_collected_site(self, mock_transfer):
        with self.assertRaises(ValueError):
            tt.pull_profile_raw(SITE)
        mock_transfer.assert_not_called()

    @patch(PATCH)
    def test_pull_slow_flux(self, mock_transfer):
        tt.pull_slow_flux('CumberlandPlain')
        mock_transfer.assert_called_once_with(
            src='uqrdm:TERNEP-Q5937/Sites/CumberlandPlain/Data/Flux/Raw/Slow',
            dst=Path('/store/Raw_data/CumberlandPlain/Flux/Slow'),
            )

    @patch(PATCH)
    def test_pull_slow_flux_rejects_non_remote_collected_site(self, mock_transfer):
        with self.assertRaises(ValueError):
            tt.pull_slow_flux(SITE)
        mock_transfer.assert_not_called()

    @patch(PATCH)
    def test_pull_rtmc_images(self, mock_transfer):
        tt.pull_rtmc_images()
        mock_transfer.assert_called_once_with(
            src='OneDrive_UoM:Documents/RTMC/Snapshots',
            dst=Path('/store/Network/RTMC'),
            )


class TestPushSiteTasks(unittest.TestCase):

    @patch(PATCH)
    def test_push_aux_fast_flux(self, mock_transfer):
        tt.push_aux_fast_flux(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/HowardSprings/Flux_aux/Fast'),
            dst='uqrdm:FLUXARCH23-Q6223/Sites/HowardSprings/Data/Flux_aux/Raw/Fast',
            exclude_dirs=['TMP'],
            timeout=1200,
            )

    @patch(PATCH)
    def test_push_main_fast_flux(self, mock_transfer):
        tt.push_main_fast_flux(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/HowardSprings/Flux/Fast'),
            dst='uqrdm:FLUXARCH23-Q6223/Sites/HowardSprings/Data/Flux/Raw/Fast',
            exclude_dirs=['TMP'],
            timeout=1200,
            )

    @patch(PATCH)
    def test_push_profile_processed(self, mock_transfer):
        tt.push_profile_processed(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Processed_data/HowardSprings/Profile'),
            dst='uqrdm:TERNEP-Q5937/Sites/HowardSprings/Data/Profile/Processed',
            )

    @patch(PATCH)
    def test_push_profile_raw(self, mock_transfer):
        tt.push_profile_raw(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/HowardSprings/Profile'),
            dst='uqrdm:TERNEP-Q5937/Sites/HowardSprings/Data/Profile/Raw',
            )

    @patch(PATCH)
    def test_push_slow_flux(self, mock_transfer):
        tt.push_slow_flux(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/HowardSprings/Flux/Slow'),
            dst='uqrdm:TERNEP-Q5937/Sites/HowardSprings/Data/Flux/Raw/Slow',
            )

    @patch(PATCH)
    def test_push_slow_flux_rejects_remote_collected_site(self, mock_transfer):
        with self.assertRaises(ValueError):
            tt.push_slow_flux('CumberlandPlain')
        mock_transfer.assert_not_called()

    @patch(PATCH)
    def test_push_cosmoz(self, mock_transfer):
        tt.push_cosmoz(SITE)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/HowardSprings/Ancillary/HowardSprings_cosmoz_CRNS.dat'),
            dst='cosmoz:/incoming/HowardSprings',
            )


class TestPushGlobalTasks(unittest.TestCase):

    @patch(PATCH)
    def test_push_site_details_json(self, mock_transfer):
        tt.push_site_details_json()
        mock_transfer.assert_called_once_with(
            src=Path('/store/Network/info/site_info.json'),
            dst='sftpgo:/web-sites/flux-status-test.tern.org.au/RTMC',
            set_modtime=False,
            )

    @patch(PATCH)
    def test_push_rtmc_toa5(self, mock_transfer):
        tt.push_rtmc_toa5()
        mock_transfer.assert_called_once_with(
            src=Path('/store/Homogenised_data/TOA5_test'),
            dst='OneDrive_UoM:Documents/RTMC/Site_data',
            timeout=180,
            dry_run=False,
            )

    @patch(PATCH)
    def test_push_rtmc_toa5_dry_run(self, mock_transfer):
        tt.push_rtmc_toa5(dry_run=True)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Homogenised_data/TOA5_test'),
            dst='OneDrive_UoM:Documents/RTMC/Site_data',
            timeout=180,
            dry_run=True,
            )

    @patch(PATCH)
    def test_push_L1_nc(self, mock_transfer):
        tt.push_L1_nc()
        mock_transfer.assert_called_once_with(
            src=Path('/store/Homogenised_data/NetCDF_test'),
            dst='uqrdm:TERNEP-Q5937/EPCN_Share/Homogenised_data/NetCDF',
            timeout=180,
            dry_run=False,
            )

    @patch(PATCH)
    def test_push_L1_nc_dry_run(self, mock_transfer):
        tt.push_L1_nc(dry_run=True)
        mock_transfer.assert_called_once_with(
            src=Path('/store/Homogenised_data/NetCDF_test'),
            dst='uqrdm:TERNEP-Q5937/EPCN_Share/Homogenised_data/NetCDF',
            timeout=180,
            dry_run=True,
            )

    def test_push_status_geojson(self):
        mock_sto = MagicMock()
        mock_sto.GEOJSON_PATH = Path('/opt/TERN_EP/network/state/network_state.json')
        with patch.dict(sys.modules, {'services.network.state_task_orchestrator': mock_sto}):
            with patch(PATCH) as mock_transfer:
                tt.push_status_geojson()
        mock_transfer.assert_called_once_with(
            src=Path('/opt/TERN_EP/network/state/network_state.json'),
            dst='sftpgo:/web-sites/flux-status-test.tern.org.au/RTMC',
            )


class TestRemoteAlias(unittest.TestCase):
    """Remote paths for aliased sites should use the alias; local paths should not."""

    @patch(PATCH)
    @patch.object(tt, 'REMOTE_COLLECTED_SITES', {'AliceSpringsMulga'})
    def test_pull_slow_flux_aliased_site(self, mock_transfer):
        tt.pull_slow_flux('AliceSpringsMulga')
        mock_transfer.assert_called_once_with(
            src='uqrdm:TERNEP-Q5937/Sites/AliceMulga/Data/Flux/Raw/Slow',
            dst=Path('/store/Raw_data/AliceSpringsMulga/Flux/Slow'),
            )

    @patch(PATCH)
    def test_push_slow_flux_aliased_site(self, mock_transfer):
        tt.push_slow_flux('AliceSpringsMulga')
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/AliceSpringsMulga/Flux/Slow'),
            dst='uqrdm:TERNEP-Q5937/Sites/AliceMulga/Data/Flux/Raw/Slow',
            )

    @patch(PATCH)
    def test_push_cosmoz_aliased_site(self, mock_transfer):
        tt.push_cosmoz('GreatWesternWoodlands')
        mock_transfer.assert_called_once_with(
            src=Path('/store/Raw_data/GreatWesternWoodlands/Ancillary/GreatWesternWoodlands_cosmoz_CRNS.dat'),
            dst='cosmoz:/incoming/GWW',
            )


if __name__ == '__main__':
    unittest.main(verbosity=2)
