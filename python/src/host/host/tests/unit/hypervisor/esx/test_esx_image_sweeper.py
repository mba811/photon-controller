# Copyright 2015 VMware, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may obtain a copy
# of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, without
# warranties or conditions of any kind, EITHER EXPRESS OR IMPLIED.  See the
# License for then specific language governing permissions and limitations
# under the License.

import errno
import shutil
import uuid
import time
import os
import tempfile
import unittest

from hamcrest import *  # noqa
from mock import MagicMock
from mock import patch
from nose_parameterized import parameterized

from common import services
from common.service_name import ServiceName
from gen.resource.ttypes import DatastoreType

from host.hypervisor.esx.image_manager import EsxImageManager
from host.hypervisor.image_manager import InvalidImageState
from host.hypervisor.image_scanner import DatastoreImageScanner
from host.hypervisor.image_sweeper import DatastoreImageSweeper

from host.hypervisor.esx.vm_config import os_vmdk_path, _disk_path


class ImageScannerTestCase(unittest.TestCase):
    DATASTORE_ID = "DS01"
    BASE_TEMP_DIR = "image_scanner"

    def setUp(self):
        self.test_dir = os.path.join(tempfile.mkdtemp(), self.BASE_TEMP_DIR)
        services.register(ServiceName.AGENT_CONFIG, MagicMock())
        self.image_manager = EsxImageManager(MagicMock(), MagicMock())
        self.vm_manager = MagicMock()
        self.image_scanner = DatastoreImageScanner(self.image_manager,
                                                   self.vm_manager,
                                                   self.DATASTORE_ID)
        self.image_scanner._task_runner = MagicMock()
        self.image_scanner._task_runner.is_stopped.return_value = False
        self.write_count = 0

        # Create various image directories and empty vmdks
        dir0 = os.path.join(self.test_dir, "images/im")

        image_id_1 = str(uuid.uuid4())
        image_id_2 = str(uuid.uuid4())
        image_id_3 = str(uuid.uuid4())
        image_id_4 = "invalid_image_id"
        self.image_ids = ["", image_id_1, image_id_2,
                          image_id_3, image_id_4]
        dir1 = os.path.join(dir0, image_id_1)
        os.makedirs(dir1)
        dir2 = os.path.join(dir0, image_id_2)
        os.makedirs(dir2)
        dir3 = os.path.join(dir0, image_id_3)
        os.makedirs(dir3)
        dir4 = os.path.join(dir0, image_id_4)
        os.makedirs(dir4)
        # Create a vmdk under "im", since the image_id is
        # not a valid uuid it should be skipped
        open(os.path.join(dir0, "im.vmdk"), 'w').close()
        # Create a good image vmdk under image_id_1, the name
        # of the vmdk matches the directory that contains it
        # so this is a valid image to remove
        vmdk_filename = image_id_1 + ".vmdk"
        open(os.path.join(dir1, vmdk_filename), 'w').close()
        # Create a good image vmdk under image_id_2, also create
        # an unused image marker file, image_id_2 should also be
        # included in the list of images to remove
        vmdk_filename = image_id_2 + ".vmdk"
        open(os.path.join(dir2, vmdk_filename), 'w').close()
        open(
            os.path.join(
                dir2,
                self.image_manager.IMAGE_MARKER_FILE_NAME),
            'w').close()
        # Don't create anything under directory dir3
        # it should still mark the image as deletable

        # Create a vmdk under an invalid image directory, since
        # the image id is not valid it should not mark it
        # for deletion
        vmdk_filename = image_id_4 + ".vmdk"
        open(os.path.join(dir4, vmdk_filename), 'w').close()

    def tearDown(self):
        shutil.rmtree(self.test_dir, True)

    @parameterized.expand([
        # path, write_count, dict_size
        (1, 1, 1),   # single good image, 1 write, 1 found
        (2, 0, 1),   # single good image, 0 writes, 1 found
        (3, 0, 0),   # single invalid image, 0 writes, 0 found
        (4, 0, 0),   # single invalid image id, 0 write, 0 found
        (0, 1, 2),   # three images, 1 writes, 2 found
    ])
    @patch("host.hypervisor.esx.image_manager."
           "EsxImageManager._write_marker_file")
    def test_image_marker(self,
                          image_id_index,
                          write_count,
                          dict_size,
                          write_marker_file):
        image_id = self.image_ids[image_id_index]
        write_marker_file.side_effect = self.fake_write_marker_file
        self.image_scanner.image_mark_rate = 60000
        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                image_id)
        dictionary = self.image_manager.\
            _mark_unused_images(self.image_scanner, good_dir)
        assert_that(len(dictionary) is dict_size)
        assert_that(self.write_count is write_count)

    def test_image_marker_bad_root(self):
        self.image_scanner.image_mark_rate = 60000
        bad_dir = os.path.join(self.test_dir,
                               "images",
                               "im",
                               "im.vmdk")
        dictionary = self.image_manager.\
            _mark_unused_images(self.image_scanner, bad_dir)
        assert_that(len(dictionary) is 0)

    def fake_write_marker_file(self, filename, content):
        basename = os.path.basename(filename)
        assert_that(basename, equal_to(
            self.image_manager.IMAGE_MARKER_FILE_NAME))
        self.write_count += 1


class ImageSweeperTestCase(unittest.TestCase):
    DATASTORE_ID = "DS01"
    BASE_TEMP_DIR = "image_sweeper"
    IMAGE_MARKER_FILENAME = EsxImageManager.IMAGE_MARKER_FILE_NAME
    IMAGE_TIMESTAMP_FILENAME = EsxImageManager.IMAGE_TIMESTAMP_FILE_NAME
    IMAGE_TOMBSTONE_FILE_NAME = EsxImageManager.IMAGE_TOMBSTONE_FILE_NAME

    def setUp(self):
        self.test_dir = os.path.join(tempfile.mkdtemp(), self.BASE_TEMP_DIR)
        services.register(ServiceName.AGENT_CONFIG, MagicMock())
        self.image_manager = EsxImageManager(MagicMock(), MagicMock())
        self.vm_manager = MagicMock()
        self.image_sweeper = DatastoreImageSweeper(self.image_manager,
                                                   self.DATASTORE_ID)
        self.image_sweeper._task_runner = MagicMock()
        self.image_sweeper._task_runner.is_stopped.return_value = False
        self.delete_count = 0

        # Create various image directories and empty vmdks
        dir0 = os.path.join(self.test_dir, "images/im")
        image_id_1 = str(uuid.uuid4())
        image_id_2 = str(uuid.uuid4())
        image_id_3 = str(uuid.uuid4())
        image_id_4 = "invalid_image_id"
        self.image_ids = ["", image_id_1, image_id_2,
                          image_id_3, image_id_4]
        dir1 = os.path.join(dir0, image_id_1)
        os.makedirs(dir1)
        dir2 = os.path.join(dir0, image_id_2)
        os.makedirs(dir2)
        dir3 = os.path.join(dir0, image_id_3)
        os.makedirs(dir3)
        dir4 = os.path.join(dir0, image_id_4)
        os.makedirs(dir4)

        # Create a vmdk under "im", since the image_id is
        # not a valid uuid it should be skipped
        open(os.path.join(dir0, "im.vmdk"), 'w').close()

        # Create a good image vmdk under image_id_1 but
        # no image marker file, this should not be deleted
        vmdk_filename = image_id_1 + ".vmdk"
        open(os.path.join(dir1, vmdk_filename), 'w').close()

        # Create a good image vmdk under image_id_2, also create
        # an unused image marker file, image_id_2 should be
        # deleted
        vmdk_filename = image_id_2 + ".vmdk"
        open(os.path.join(dir2, vmdk_filename), 'w').close()
        open(os.path.join(
            dir2, self.IMAGE_MARKER_FILENAME), 'w').close()

        # Create a marker file under dir3 but no
        # vmdk file. It should be deleted as well
        open(os.path.join(
            dir3, self.IMAGE_MARKER_FILENAME), 'w').close()

        # Create a vmdk under an invalid image directory,
        # also create a marker file. Since the image_id
        # is not valid it should not be deleted
        vmdk_filename = image_id_4 + ".vmdk"
        open(os.path.join(dir4, vmdk_filename), 'w').close()
        open(os.path.join(
            dir4, self.IMAGE_MARKER_FILENAME), 'w').close()

    def tearDown(self):
        shutil.rmtree(self.test_dir, True)

    @parameterized.expand([
        # image_id, target image_id, delete count
        (1, 1, 0),  # 1 image, no marker file, 0 delete
        (2, 2, 1),  # 1 image, marker file, 1 delete
        (3, 3, 1),  # 0 image, marker file, 1 delete
        (4, 4, 0),  # 1 image, marker file, 0 delete (invalid image id)
        (2, 1, 0)   # 1 image, marker file, 0 delete
                    # incorrect target image
    ])
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._delete_single_image")
    def test_image_sweeper(self,
                           image_id_index,
                           target_image_id_index,
                           deleted_count,
                           delete_single_image):
        delete_single_image.side_effect = \
            self.patched_delete_single_image

        self.image_sweeper.image_sweep_rate = 60000

        image_id = self.image_ids[image_id_index]
        target_image_id = self.image_ids[target_image_id_index]
        self.image_sweeper.set_target_images([target_image_id])
        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                image_id)
        deleted_list = self.image_manager.\
            _delete_unused_images(self.image_sweeper, good_dir)
        assert_that(len(deleted_list) is deleted_count)
        assert_that(self.delete_count is deleted_count)

    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._delete_single_image")
    def test_image_sweeper_bad_root(self, delete_single_image):
        delete_single_image.side_effect = \
            self.patched_delete_single_image
        self.image_sweeper.image_sweep_rate = 60000
        self.image_sweeper.set_target_images(["image_id_5"])
        bad_dir = os.path.join(self.test_dir,
                               "images",
                               "im",
                               "im.vmdk")
        dictionary = self.image_manager.\
            _delete_unused_images(self.image_sweeper, bad_dir)
        assert_that(len(dictionary) is 0)
        assert_that(self.delete_count is 0)

    def patched_delete_single_image(self, image_sweeper,
                                    pathname, image_id):
        self.delete_count += 1
        return True


class ImageSweeperDeleteSingleImageTestCase(unittest.TestCase):
    DATASTORE_ID = "DS01"
    BASE_TEMP_DIR = "delete_single_image"
    IMAGE_MARKER_FILENAME = \
        EsxImageManager.IMAGE_MARKER_FILE_NAME
    IMAGE_TIMESTAMP_FILENAME = \
        EsxImageManager.IMAGE_TIMESTAMP_FILE_NAME
    IMAGE_TIMESTAMP_FILE_RENAME_SUFFIX = \
        EsxImageManager.IMAGE_TIMESTAMP_FILE_RENAME_SUFFIX

    def setUp(self):
        self.test_dir = os.path.join(tempfile.mkdtemp(), self.BASE_TEMP_DIR)
        self.gc_dir = os.path.join(tempfile.mkdtemp(), self.BASE_TEMP_DIR)
        services.register(ServiceName.AGENT_CONFIG, MagicMock())
        self.image_manager = EsxImageManager(MagicMock(), MagicMock())
        self.vm_manager = MagicMock()
        self.image_sweeper = DatastoreImageSweeper(self.image_manager,
                                                   self.DATASTORE_ID)
        self.deleted = False
        self.marker_unlinked = False

        # Create various image directories and empty vmdks
        dir0 = os.path.join(self.test_dir, "images/im")
        image_id_1 = str(uuid.uuid4())
        image_id_2 = str(uuid.uuid4())
        image_id_3 = str(uuid.uuid4())
        image_id_4 = str(uuid.uuid4())

        self.image_id_1 = image_id_1
        self.image_id_2 = image_id_2
        self.image_id_3 = image_id_3
        self.image_id_4 = image_id_4

        dir1 = os.path.join(dir0, image_id_1)
        os.makedirs(dir1)
        dir2 = os.path.join(dir0, image_id_2)
        os.makedirs(dir2)
        dir3 = os.path.join(dir0, image_id_3)
        os.makedirs(dir3)
        dir4 = os.path.join(dir0, image_id_4)
        os.makedirs(dir4)

        self.marker_file_content_time = 0
        self.timestamp_file_mod_time = 0
        self.renamed_timestamp_file_mod_time = 0

        # Create a good image vmdk under image_id_1,
        # also create a valid image marker file
        # and a valid timestamp file
        vmdk_filename = image_id_1 + ".vmdk"
        open(os.path.join(dir1, vmdk_filename), 'w').close()
        timestamp_filename = \
            os.path.join(dir1, self.IMAGE_TIMESTAMP_FILENAME)
        open(timestamp_filename, 'w').close()
        marker_filename = \
            os.path.join(dir1, self.IMAGE_MARKER_FILENAME)
        open(marker_filename, 'w').close()

        # Create a good image vmdk under image_id_2,
        # create timestamp but no image marker file,
        vmdk_filename = image_id_2 + ".vmdk"
        open(os.path.join(dir2, vmdk_filename), 'w').close()
        timestamp_filename = \
            os.path.join(dir2, self.IMAGE_TIMESTAMP_FILENAME)
        open(timestamp_filename, 'w').close()

        # Create a good image vmdk under image_id_3,
        # create image_marker file but no timestamp
        # and no renamed timestamp file
        vmdk_filename = image_id_3 + ".vmdk"
        open(os.path.join(dir3, vmdk_filename), 'w').close()
        marker_filename = \
            os.path.join(dir3, self.IMAGE_MARKER_FILENAME)
        open(marker_filename, 'w').close()

        # Create a good image vmdk under image_id_4,
        # create image_marker file, renamed timestamp file
        # but no timestamp file
        vmdk_filename = image_id_4 + ".vmdk"
        open(os.path.join(dir4, vmdk_filename), 'w').close()
        marker_filename = \
            os.path.join(dir4, self.IMAGE_MARKER_FILENAME)
        open(marker_filename, 'w').close()
        timestamp_filename = \
            os.path.join(dir4, self.IMAGE_TIMESTAMP_FILENAME)
        renamed_timestamp_filename = \
            timestamp_filename + \
            self.IMAGE_TIMESTAMP_FILE_RENAME_SUFFIX
        open(renamed_timestamp_filename, 'w').close()

    def tearDown(self):
        shutil.rmtree(self.test_dir, True)
        shutil.rmtree(self.gc_dir, True)

    # The following test plays with the content of
    # marker file (a timestamp) and the mod time of
    # the image timestamp file before and after rename.
    # It should delete the image only if
    # marker - grace period > timestamp AND
    # timestamp == timestamp after rename
    # All the other cases should point to the fact
    # that the image has been used after the image
    # scan started. To avoid problems due to
    # non synchronized clocks on different hosts
    # a grace period of 10 minutes is applied on
    # the timestamp from the marker file
    @parameterized.expand([
        # marker time, mod time, mod time after rename, deleted
        (1061, 1000, 1000, True),
        (1060, 1000, 1000, False),
        (1000, 1000, 1000, False),
        (1000, 1001, 1001, False),
        (2000, 1000, 2010, False)
    ])
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._read_marker_file")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._get_datastore_type")
    @patch("host.hypervisor.esx.image_manager."
           "EsxImageManager._get_mod_time")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rename")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_unlink")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rm_rf")
    def test_delete_single_image(
            self,
            marker_file_content_time,
            timestamp_file_mod_time,
            renamed_timestamp_file_mod_time,
            deleted,
            rm_rf,
            unlink,
            rename,
            get_mod_time,
            get_datastore_type,
            read_marker_file):

        self.marker_file_content_time = \
            marker_file_content_time
        self.timestamp_file_mod_time = \
            timestamp_file_mod_time
        self.renamed_timestamp_file_mod_time = \
            renamed_timestamp_file_mod_time
        marker_unlinked = not deleted

        read_marker_file.side_effect = \
            self.patched_read_marker_file
        get_datastore_type.side_effect = \
            self.patched_get_datastore_type
        get_mod_time.side_effect = \
            self.patched_get_mod_time
        rename.side_effect = self.patched_rename
        unlink.side_effect = self.patched_unlink
        rm_rf.side_effect = self.patched_rm_rf

        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                self.image_id_1)
        ret = self.image_manager.\
            _delete_single_image(self.image_sweeper,
                                 good_dir,
                                 self.image_id_1)

        assert_that(deleted is ret)
        assert_that(deleted is self.deleted)
        assert_that(marker_unlinked is self.marker_unlinked)

    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._get_datastore_type")
    @patch("host.hypervisor.esx.image_manager."
           "EsxImageManager._get_mod_time")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rename")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rm_rf")
    def test_delete_single_image_no_marker_file(
            self,
            rm_rf,
            rename,
            get_mod_time,
            get_datastore_type):

        get_datastore_type.side_effect = \
            self.patched_get_datastore_type

        get_mod_time.side_effect = \
            self.patched_get_mod_time

        rename.side_effect = self.patched_rename
        rm_rf.side_effect = self.patched_rm_rf

        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                self.image_id_2)
        deleted = self.image_manager.\
            _delete_single_image(self.image_sweeper,
                                 good_dir,
                                 self.image_id_2)

        assert_that(deleted is False)
        assert_that(self.deleted is False)

    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._read_marker_file")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._get_datastore_type")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rename")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rm_rf")
    def test_delete_single_image_no_timestamp_files(
            self,
            rm_rf,
            rename,
            get_datastore_type,
            read_marker_file):

        read_marker_file.side_effect = \
            self.patched_read_marker_file

        get_datastore_type.side_effect = \
            self.patched_get_datastore_type

        rename.side_effect = self.patched_rename
        rm_rf.side_effect = self.patched_rm_rf

        self.marker_file_content_time = 1000
        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                self.image_id_3)
        deleted = self.image_manager.\
            _delete_single_image(self.image_sweeper,
                                 good_dir,
                                 self.image_id_3)

        assert_that(deleted is True)
        assert_that(self.deleted is True)

    @parameterized.expand([
        # marker time, mod time, mod time after rename, deleted
        (1061, 1000, True),
        (1060, 1000, False),
        (1000, 1000, False),
        (1000, 1001, False)
    ])
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._read_marker_file")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._get_datastore_type")
    @patch("host.hypervisor.esx.image_manager."
           "EsxImageManager._get_mod_time")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rename")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_unlink")
    @patch("host.hypervisor.esx."
           "image_manager.EsxImageManager._image_sweeper_rm_rf")
    def test_delete_single_image_no_timestamp_file(
            self,
            marker_file_content_time,
            renamed_timestamp_file_mod_time,
            deleted,
            rm_rf,
            unlink,
            rename,
            get_mod_time,
            get_datastore_type,
            read_marker_file):

        self.marker_file_content_time = \
            marker_file_content_time
        self.renamed_timestamp_file_mod_time = \
            renamed_timestamp_file_mod_time
        marker_unlinked = not deleted

        read_marker_file.side_effect = \
            self.patched_read_marker_file
        get_datastore_type.side_effect = \
            self.patched_get_datastore_type
        get_mod_time.side_effect = \
            self.patched_get_mod_time
        rename.side_effect = self.patched_rename
        unlink.side_effect = self.patched_unlink
        rm_rf.side_effect = self.patched_rm_rf

        good_dir = os.path.join(self.test_dir,
                                "images",
                                "im",
                                self.image_id_4)
        ret = self.image_manager.\
            _delete_single_image(self.image_sweeper,
                                 good_dir,
                                 self.image_id_4)

        assert_that(deleted is ret)
        assert_that(deleted is self.deleted)
        assert_that(marker_unlinked is self.marker_unlinked)

    def patched_read_marker_file(self, filename):
        if not os.path.exists(filename):
            raise OSError
        return self.marker_file_content_time

    def patched_get_datastore_type(self, datastore_id):
        return DatastoreType.EXT3

    def patched_get_mod_time(self, filename):
        try:
            os.path.getmtime(filename)
        except OSError as ex:
            if ex.errno == errno.ENOENT:
                return False, 0
            else:
                raise ex
        # fix mod_time
        if filename.endswith(
                self.IMAGE_TIMESTAMP_FILE_RENAME_SUFFIX):
            mod_time = self.renamed_timestamp_file_mod_time
        else:
            mod_time = self.timestamp_file_mod_time
        return True, mod_time

    def patched_rename(self, source, destination):
        if source.endswith(self.IMAGE_TIMESTAMP_FILENAME):
            shutil.move(source, destination)
        else:
            shutil.move(source, self.gc_dir)

    def patched_unlink(self, target):
        self.marker_unlinked = True

    def patched_rm_rf(self, target):
        self.deleted = True


class ImageSweeperTouchTimestampTestCase(unittest.TestCase):
    DATASTORE_ID = "DS01"
    BASE_TEMP_DIR = "image_sweeper"
    IMAGE_TIMESTAMP_FILENAME = EsxImageManager.IMAGE_TIMESTAMP_FILE_NAME
    IMAGE_TOMBSTONE_FILENAME = EsxImageManager.IMAGE_TOMBSTONE_FILE_NAME

    def setUp(self):
        self.test_dir = os.path.join(tempfile.mkdtemp(), self.BASE_TEMP_DIR)
        services.register(ServiceName.AGENT_CONFIG, MagicMock())
        self.image_manager = EsxImageManager(MagicMock(), MagicMock())
        self.vm_manager = MagicMock()
        self.image_sweeper = DatastoreImageSweeper(self.image_manager,
                                                   self.DATASTORE_ID)
        self.image_sweeper._task_runner = MagicMock()
        self.image_sweeper._task_runner.is_stopped.return_value = False
        self.delete_count = 0

        # Create various image directories and empty vmdks
        dir0 = os.path.join(self.test_dir, self.DATASTORE_ID, "images/im")
        self.dir0 = dir0

        # Image dir with correct timestamp file
        image_id_1 = str(uuid.uuid4())
        dir1 = self.create_dir(image_id_1)
        open(os.path.join(
            dir1, self.IMAGE_TIMESTAMP_FILENAME), 'w').close()

        # Image dir without the correct timestamp file
        image_id_2 = str(uuid.uuid4())
        dir2 = self.create_dir(image_id_2)

        # Image dir with correct timestamp file
        # and with tombstone file
        image_id_3 = str(uuid.uuid4())
        dir3 = self.create_dir(image_id_3)
        open(os.path.join(
            dir3, self.IMAGE_TIMESTAMP_FILENAME), 'w').close()
        open(os.path.join(
            dir3, self.IMAGE_TOMBSTONE_FILENAME), 'w').close()

        self.image_ids = ["", image_id_1, image_id_2, image_id_3]
        self.image_dirs = ["", dir1, dir2, dir3]

    def tearDown(self):
        shutil.rmtree(self.test_dir, True)

    @parameterized.expand([
        # timestamp_exists, tombstone_exists
        (True, False),
        (True, True),
        (False, False)
    ])
    # The os_vmdk_path method is defined in vm_config.py
    # but it is imported in esx/image_manager.py, that is
    # the instance we need to patch
    @patch("host.hypervisor.esx.image_manager.os_vmdk_path")
    def test_touch_timestamp_file(self,
                                  timestamp_exists,
                                  tombstone_exists,
                                  os_vmdk_path):
        if tombstone_exists:
            image_index = 3
            exception_class = type(InvalidImageState())
        elif not timestamp_exists:
            image_index = 2
            exception_class = type(OSError())
        else:
            image_index = 1
            exception_class = None

        image_id = self.image_ids[image_index]
        image_dir = self.image_dirs[image_index]
        os_vmdk_path.side_effect = self.patched_os_vmdk_path

        timestamp_filename_path = \
            os.path.join(image_dir, self.IMAGE_TIMESTAMP_FILENAME)

        pre_mod_time = 0

        if timestamp_exists:
            # save mod time on the image timestamp file
            pre_mod_time = os.path.getmtime(timestamp_filename_path)

        try:
            time.sleep(1)
            self.image_manager.\
                touch_image_timestamp(self.DATASTORE_ID,
                                      image_id)
            assert_that(exception_class is None)
            # check new timestamp
            post_mod_time = os.path.getmtime(timestamp_filename_path)
            assert_that((post_mod_time > pre_mod_time) is True)
        except Exception as ex:
            assert_that((type(ex) == exception_class) is True)

    @patch("host.hypervisor.esx.image_manager.os_vmdk_path")
    def test_create_tombstone_file(self,
                                   os_vmdk_path):
        image_index = 1

        image_id = self.image_ids[image_index]
        image_dir = self.image_dirs[image_index]
        os_vmdk_path.side_effect = self.patched_os_vmdk_path

        tombstone_filename_path = \
            os.path.join(image_dir, self.IMAGE_TOMBSTONE_FILENAME)

        self.image_manager.create_image_tombstone(self.DATASTORE_ID,
                                                  image_id)

        # check tombstone exists
        exists = os.path.exists(tombstone_filename_path)
        assert_that(exists is True)

    def patched_os_vmdk_path(self, datastore, disk_id, folder):
        folder = self.dir0
        ret = os_vmdk_path(datastore, disk_id, folder)
        return ret

    def create_dir(self, image_id):
        dirname = os.path.join(self.dir0,
                               _disk_path(image_id))
        os.makedirs(dirname)
        return dirname
