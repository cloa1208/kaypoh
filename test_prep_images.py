#!/usr/bin/env python3
"""Offline tests for the HTML image-rewrite logic in prep_images.py.

Standard library only, no network: the download/resize step is injected as a
stub, so nothing is ever fetched or shrunk for real.
"""
import os
import re
import sys
import shutil
import subprocess
import tempfile
import unittest

import prep_images as pi

HERE = os.path.dirname(os.path.abspath(__file__))


def stub_writer(in_size, out_size):
    """Return a fetch_and_shrink stub plus a list of the URLs it sees.

    The stub writes `in_size` bytes to the .orig path and `out_size` bytes to
    the .jpg path, mimicking a successful download + resize without touching
    the network.
    """
    fetched = []

    def fetch_and_shrink(url, raw_path, out_path):
        fetched.append(url)
        with open(raw_path, "wb") as f:
            f.write(b"x" * in_size)
        with open(out_path, "wb") as f:
            f.write(b"y" * out_size)

    return fetch_and_shrink, fetched


class RewriteHtmlTests(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(prefix="kaypoh-test-")
        self.html_dir = os.path.join(self.base, "html")
        self.imgdir = os.path.join(self.base, "img")
        os.makedirs(self.html_dir)
        os.makedirs(self.imgdir)

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def test_repeated_url_fetched_once_both_rewritten(self):
        # two DISTINCT urls; the first appears twice in the HTML
        html = ('<img src="http://ex/y.jpg">'
                '<img src="http://ex/y.jpg">'
                '<img src="http://ex/z.jpg">')
        fetch_and_shrink, fetched = stub_writer(3000, 1000)
        new_html, n_urls, total_in, total_out = pi.rewrite_html(
            html, self.html_dir, self.imgdir, fetch_and_shrink)
        # each distinct URL is deduped to a single fetch
        self.assertEqual(fetched.count("http://ex/y.jpg"), 1)
        self.assertEqual(fetched.count("http://ex/z.jpg"), 1)
        self.assertEqual(len(fetched), 2)
        # the returned count is the number of distinct URLs
        self.assertEqual(n_urls, 2)
        # total_in/total_out include both images
        self.assertEqual(total_in, 6000)
        self.assertEqual(total_out, 2000)
        # every occurrence is rewritten to a relative local path
        srcs = re.findall(r'src="([^"]+)"', new_html)
        self.assertEqual(len(srcs), 3)
        self.assertEqual(srcs[0], srcs[1])      # the two y.jpg tags share one file
        self.assertNotEqual(srcs[0], srcs[2])    # z.jpg is a distinct file
        for src in srcs:
            self.assertFalse(src.startswith("http://"))
            self.assertTrue(os.path.exists(os.path.join(self.html_dir, src)))
        self.assertNotIn("http://ex/", new_html)

    def test_amp_and_raw_variant_fetched_once(self):
        # same image, two raw forms: one with & and one with &amp;
        html = ('<img src="http://ex/p.jpg?x=1&y=2">'
                '<img src="http://ex/p.jpg?x=1&amp;y=2">')
        fetch_and_shrink, fetched = stub_writer(3000, 1000)
        new_html, n_urls, total_in, total_out = pi.rewrite_html(
            html, self.html_dir, self.imgdir, fetch_and_shrink)
        # the two raw forms decode to one url, so it is fetched exactly once
        self.assertEqual(len(fetched), 1)
        self.assertEqual(fetched[0], "http://ex/p.jpg?x=1&y=2")
        # both raw src occurrences point at the same single local file
        srcs = re.findall(r'src="([^"]+)"', new_html)
        self.assertEqual(len(srcs), 2)
        self.assertEqual(srcs[0], srcs[1])
        self.assertFalse(srcs[0].startswith("http://"))
        self.assertTrue(os.path.exists(os.path.join(self.html_dir, srcs[0])))
        self.assertEqual(len(os.listdir(self.imgdir)), 1)
        # count is the number of distinct decoded urls, not raw occurrences
        self.assertEqual(n_urls, 1)

    def test_amp_entity_fetched_with_ampersand(self):
        html = '<img src="http://ex/p.jpg?x=1&amp;y=2">'
        fetched = []

        def fetch_and_shrink(url, raw_path, out_path):
            fetched.append(url)
            with open(raw_path, "wb") as f:
                f.write(b"x" * 2000)
            with open(out_path, "wb") as f:
                f.write(b"y" * 500)

        new_html, *_ = pi.rewrite_html(html, self.html_dir, self.imgdir, fetch_and_shrink)
        self.assertEqual(len(fetched), 1)
        # the &amp; in the HTML is decoded to & for the fetch URL
        self.assertEqual(fetched[0], "http://ex/p.jpg?x=1&y=2")
        # and the hotlink (with its &amp;) is gone from the rewritten HTML
        self.assertNotIn("&amp;", new_html)
        self.assertNotIn("http://ex/p.jpg", new_html)

    def test_failed_fetch_keeps_hotlink_and_no_partial_files(self):
        html = '<img src="http://ex/missing.jpg">'
        calls = {"n": 0}

        def failing(url, raw_path, out_path):
            calls["n"] += 1
            # simulate a partial download + partial output before the error
            with open(raw_path, "wb") as f:
                f.write(b"partial-orig")
            with open(out_path, "wb") as f:
                f.write(b"partial-jpg")
            raise RuntimeError("network down")

        new_html, n_urls, total_in, total_out = pi.rewrite_html(
            html, self.html_dir, self.imgdir, failing)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(n_urls, 1)
        # hotlink kept: the HTML is returned unchanged
        self.assertEqual(new_html, html)
        self.assertEqual(total_in, 0)
        self.assertEqual(total_out, 0)
        # no .orig or .jpg left behind
        self.assertEqual(sorted(os.listdir(self.imgdir)), [])

    def test_src_relative_to_html_dir(self):
        html = '<img src="http://ex/z.jpg">'
        fetch_and_shrink, fetched = stub_writer(1000, 500)
        new_html, *_ = pi.rewrite_html(html, self.html_dir, self.imgdir, fetch_and_shrink)
        srcs = re.findall(r'src="([^"]+)"', new_html)
        self.assertEqual(len(srcs), 1)
        rel = srcs[0]
        # relative (not absolute) and resolves to the real output file
        self.assertFalse(os.path.isabs(rel))
        resolved = os.path.normpath(os.path.join(self.html_dir, rel))
        self.assertTrue(os.path.exists(resolved))
        self.assertTrue(resolved.endswith(".jpg"))


class NoArgTests(unittest.TestCase):
    def test_no_argument_exits_2(self):
        script = os.path.join(HERE, "prep_images.py")
        result = subprocess.run([sys.executable, script],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
