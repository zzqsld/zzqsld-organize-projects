# test_basic.py

import unittest
from pathlib import Path
from organize_projects.organize_projects import (
    has_chinese,
    unique_path,
    move_file,
    convert_docx_to_pdf,
    merge_pdfs,
    find_subfolders_1_to_12,
    calculate_md5,
    remove_duplicate_files,
)

class TestOrganizeProjects(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("test_dir")
        self.test_dir.mkdir(exist_ok=True)

    def tearDown(self):
        for item in self.test_dir.iterdir():
            if item.is_dir():
                item.rmdir()
            else:
                item.unlink()
        self.test_dir.rmdir()

    def test_has_chinese(self):
        self.assertTrue(has_chinese("测试"))
        self.assertFalse(has_chinese("Test"))

    def test_unique_path(self):
        existing_file = self.test_dir / "file.txt"
        existing_file.touch()
        unique_file = unique_path(self.test_dir / "file.txt")
        self.assertNotEqual(unique_file.name, "file.txt")
        self.assertTrue(unique_file.name.startswith("file ("))

    def test_move_file(self):
        src_file = self.test_dir / "source.txt"
        dst_file = self.test_dir / "destination.txt"
        src_file.touch()
        move_file(src_file, dst_file)
        self.assertFalse(src_file.exists())
        self.assertTrue(dst_file.exists())

    def test_convert_docx_to_pdf(self):
        # This test requires a valid .docx file to be present
        # You can create a mock or use a sample file for testing
        pass

    def test_merge_pdfs(self):
        # This test requires valid PDF files to be present
        # You can create mock PDFs or use sample files for testing
        pass

    def test_find_subfolders_1_to_12(self):
        for i in range(1, 13):
            (self.test_dir / str(i)).mkdir()
        missing = find_subfolders_1_to_12(self.test_dir)
        self.assertEqual(missing, [])

    def test_calculate_md5(self):
        test_file = self.test_dir / "test.txt"
        test_file.write_text("Hello World")
        md5 = calculate_md5(test_file)
        self.assertIsNotNone(md5)

    def test_remove_duplicate_files(self):
        # This test requires valid PDF files to be present
        # You can create mock PDFs or use sample files for testing
        pass

if __name__ == "__main__":
    unittest.main()