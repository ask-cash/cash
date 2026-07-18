"""Server-side media duration enforcement."""

from __future__ import annotations

import os
import subprocess
import unittest
from unittest.mock import patch

from services import transcription


class MediaDurationTest(unittest.TestCase):
    def test_duration_within_limit_is_accepted(self):
        result = subprocess.CompletedProcess([], 0, stdout="89.75\n", stderr="")
        with patch.dict(os.environ, {"VOICE_MAX_SECONDS": "90"}), patch(
            "services.transcription.subprocess.run",
            return_value=result,
        ):
            self.assertEqual(transcription.validate_media_duration("/tmp/voice.webm"), 89.75)

    def test_duration_over_limit_is_rejected(self):
        result = subprocess.CompletedProcess([], 0, stdout="91\n", stderr="")
        with patch.dict(os.environ, {"VOICE_MAX_SECONDS": "90"}), patch(
            "services.transcription.subprocess.run",
            return_value=result,
        ), self.assertRaises(transcription.TranscriptionError) as raised:
            transcription.validate_media_duration("/tmp/voice.webm")
        self.assertEqual(raised.exception.code, "media_too_long")
        self.assertEqual(raised.exception.status_code, 413)

    def test_invalid_container_is_rejected(self):
        with patch(
            "services.transcription.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["ffprobe"]),
        ), self.assertRaises(transcription.TranscriptionError) as raised:
            transcription.media_duration_seconds("/tmp/not-media")
        self.assertEqual(raised.exception.code, "invalid_media")
        self.assertEqual(raised.exception.status_code, 415)


if __name__ == "__main__":
    unittest.main()
