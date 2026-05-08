"""Unit tests for organizer.rules classification and scoring logic."""

import time
import unittest
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from organizer.categorize import _process_one
from organizer.rules import (
    classify_email,
    is_important_signal,
    is_protected,
    score_priority,
)
from organizer.utils import gmail_execute


class TestClassifyEmail(unittest.TestCase):
    """Tests for classify_email covering all five output categories."""

    def _classify(  # pylint: disable=too-many-arguments
        # pylint: disable=too-many-positional-arguments
        self,
        subject: str,
        sender: str,
        snippet: str = "",
        has_unsubscribe: bool = False,
        gmail_labels: list = None,
        replied_to: bool = False,
    ) -> str:
        """Convenience wrapper with sensible defaults."""
        return classify_email(
            subject,
            sender,
            snippet,
            has_unsubscribe,
            gmail_labels or [],
            replied_to,
        )

    def test_receipt_amazon_order_confirmation(self):
        """Order confirmation from Amazon domain → Receipts."""
        result = self._classify(
            subject="Your order has been confirmed",
            sender="order-update@amazon.com",
        )
        self.assertEqual(result, "Receipts")

    def test_receipt_subject_keyword(self):
        """Receipt keyword in subject → Receipts regardless of domain."""
        result = self._classify(
            subject="Your receipt from Starbucks",
            sender="no-reply@starbucks.com",
        )
        self.assertEqual(result, "Receipts")

    def test_promotions_mailchimp_domain(self):
        """Known ESP domain → Promotions."""
        result = self._classify(
            subject="Check out our new products",
            sender="news@mailchimp.com",
        )
        self.assertEqual(result, "Promotions")

    def test_promotions_unsubscribe_header(self):
        """List-Unsubscribe header → Promotions."""
        result = self._classify(
            subject="Weekly deals just for you",
            sender="deals@somestore.com",
            has_unsubscribe=True,
        )
        self.assertEqual(result, "Promotions")

    def test_promotions_promo_subject(self):
        """Promotional subject keyword → Promotions."""
        result = self._classify(
            subject="50% off everything — today only!",
            sender="offers@retailsite.com",
        )
        self.assertEqual(result, "Promotions")

    def test_important_payment_due(self):
        """'Payment due' billing override → Important."""
        result = self._classify(
            subject="Payment Due: Invoice #12345",
            sender="billing@somecompany.com",
        )
        self.assertEqual(result, "Important")

    def test_important_vip_domain(self):
        """VIP domain (meadeengineering.com) → Important."""
        result = self._classify(
            subject="Project update",
            sender="manager@meadeengineering.com",
        )
        self.assertEqual(result, "Important")

    def test_personal_gmail_sender(self):
        """Sender from gmail.com with human-looking local → Personal."""
        result = self._classify(
            subject="Hey, are you free Friday?",
            sender="john.smith@gmail.com",
        )
        self.assertEqual(result, "Personal")

    def test_junk_noreply_sender(self):
        """noreply local part → Junk (neutral subject, no promo match)."""
        result = self._classify(
            subject="General update from service",
            sender="noreply@someservice.com",
        )
        self.assertEqual(result, "Junk")

    def test_junk_security_code_subject(self):
        """Security code subject → Junk (beats other checks)."""
        result = self._classify(
            subject="Your verification code is 123456",
            sender="security@gmail.com",
        )
        self.assertEqual(result, "Junk")

    def test_junk_social_notification(self):
        """Social activity notification → Junk."""
        result = self._classify(
            subject="John liked your post",
            sender="notification@instagram.com",
        )
        self.assertEqual(result, "Junk")

    def test_promotions_gmail_category_label(self):
        """CATEGORY_PROMOTIONS Gmail label → Promotions."""
        result = self._classify(
            subject="Check out our newsletter",
            sender="hello@somecompany.com",
            gmail_labels=["CATEGORY_PROMOTIONS"],
        )
        self.assertEqual(result, "Promotions")

    def test_personal_replied_to_real_person(self):
        """Replied-to + real person pattern → Personal."""
        result = self._classify(
            subject="Following up",
            sender="alice.jones@corporate.com",
            replied_to=True,
        )
        self.assertEqual(result, "Personal")

    def test_important_invoice_subject(self):
        """Invoice keyword in subject → Important."""
        result = self._classify(
            subject="Invoice #4567 for services rendered",
            sender="accounting@vendor.com",
        )
        self.assertEqual(result, "Important")


class TestIsProtected(unittest.TestCase):
    """Tests for is_protected domain and keyword matching."""

    def test_exact_protected_domain(self):
        """Exact match on asu.edu → protected."""
        self.assertTrue(is_protected("Enrollment", "advisor@asu.edu"))

    def test_protected_subdomain_suffix(self):
        """Subdomain of masuk.org → protected."""
        self.assertTrue(
            is_protected("Update", "info@mail.masuk.org")
        )

    def test_protected_keyword_in_subject(self):
        """Protected keyword in subject → protected."""
        self.assertTrue(
            is_protected("Your FAFSA application", "aid@school.edu")
        )

    def test_protected_keyword_in_snippet(self):
        """Protected keyword appearing only in snippet → protected."""
        self.assertTrue(
            is_protected(
                "Important update",
                "noreply@example.com",
                snippet="Your tuition payment is due",
            )
        )

    def test_protected_monroe_ct_domain(self):
        """Exact match on monroe.ct.us → protected."""
        self.assertTrue(
            is_protected("Notice", "info@monroe.ct.us")
        )

    def test_non_protected_email(self):
        """Random commercial email → not protected."""
        self.assertFalse(
            is_protected("Sale today!", "promo@amazon.com")
        )

    def test_non_protected_no_keyword(self):
        """Generic sender with no protected keyword → not protected."""
        self.assertFalse(
            is_protected("Hello there", "friend@gmail.com")
        )


class TestIsImportantSignal(unittest.TestCase):
    """Tests for is_important_signal importance detection."""

    def test_real_person_sender_is_important(self):
        """Real-person sender → important signal."""
        self.assertTrue(
            is_important_signal(
                subject="Lunch tomorrow?",
                sender="jane.doe@gmail.com",
                snippet="",
                age_days=2.0,
                is_unread=True,
                replied_to=False,
            )
        )

    def test_important_keyword_in_subject(self):
        """Importance keyword in subject → important signal."""
        self.assertTrue(
            is_important_signal(
                subject="Invoice overdue — please pay",
                sender="billing@vendor.com",
                snippet="",
                age_days=5.0,
                is_unread=False,
                replied_to=False,
            )
        )

    def test_important_keyword_in_snippet(self):
        """Importance keyword in snippet → important signal."""
        self.assertTrue(
            is_important_signal(
                subject="Update from vendor",
                sender="noreply@vendor.com",
                snippet="Your invoice is past due",
                age_days=10.0,
                is_unread=False,
                replied_to=False,
            )
        )

    def test_unread_young_message_is_important(self):
        """Unread message younger than 90 days → important signal."""
        self.assertTrue(
            is_important_signal(
                subject="Some bulk newsletter",
                sender="news@bulkmailer.com",
                snippet="",
                age_days=30.0,
                is_unread=True,
                replied_to=False,
            )
        )

    def test_replied_to_sender_is_important(self):
        """Previously-replied-to sender → important signal."""
        self.assertTrue(
            is_important_signal(
                subject="Following up",
                sender="noreply@company.com",
                snippet="",
                age_days=100.0,
                is_unread=False,
                replied_to=True,
            )
        )

    def test_old_automated_not_important(self):
        """Old automated email with no signals → not important."""
        self.assertFalse(
            is_important_signal(
                subject="Your weekly digest",
                sender="noreply@newsletter.com",
                snippet="",
                age_days=200.0,
                is_unread=False,
                replied_to=False,
            )
        )


class TestScorePriority(unittest.TestCase):
    """Tests for score_priority scoring logic and bounds."""

    def test_high_score_real_person_urgent_recent(self):
        """Real person + urgent keyword + recent message → high score."""
        score = score_priority(
            subject="Urgent: invoice due",
            sender="boss@gmail.com",
            is_unread=True,
            age_days=1.0,
            replied_to=True,
            gmail_labels=[],
        )
        self.assertGreaterEqual(score, 8)

    def test_low_score_automated_old(self):
        """Old automated email with no urgency → low score."""
        score = score_priority(
            subject="Your weekly digest",
            sender="noreply@newsletter.com",
            is_unread=False,
            age_days=60.0,
            replied_to=False,
            gmail_labels=["CATEGORY_PROMOTIONS"],
        )
        self.assertLessEqual(score, 3)

    def test_score_minimum_is_one(self):
        """Score is never below 1."""
        score = score_priority(
            subject="",
            sender="noreply@junk.com",
            is_unread=False,
            age_days=365.0,
            replied_to=False,
            gmail_labels=["CATEGORY_PROMOTIONS"],
        )
        self.assertGreaterEqual(score, 1)

    def test_score_maximum_is_ten(self):
        """Score is never above 10."""
        score = score_priority(
            subject=(
                "Urgent urgent urgent invoice deadline appointment "
                "contract offer renewal"
            ),
            sender="person@gmail.com",
            is_unread=True,
            age_days=0.1,
            replied_to=True,
            gmail_labels=[],
        )
        self.assertLessEqual(score, 10)

    def test_score_within_bounds_general(self):
        """Score always falls within 1-10."""
        for age in (0.5, 7, 30, 90, 365):
            score = score_priority(
                subject="Meeting request",
                sender="colleague@company.com",
                is_unread=True,
                age_days=age,
                replied_to=False,
                gmail_labels=[],
            )
            self.assertTrue(1 <= score <= 10, f"score={score} out of range")


class TestDryRunSafety(unittest.TestCase):
    """Verify --dry-run makes zero write calls to the Gmail API."""

    def _make_msg(
        self,
        subject: str = "Test",
        sender: str = "noreply@bulk.com",
        age_days: float = 60.0,
        snippet: str = "",
        labels: list = None,
    ) -> dict:
        """Build a minimal fake Gmail message dict."""
        ts_ms = int(
            (time.time() - age_days * 86400) * 1000
        )
        return {
            "id": "abc123",
            "snippet": snippet,
            "internalDate": str(ts_ms),
            "labelIds": labels or [],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                    {"name": "List-Unsubscribe", "value": ""},
                ]
            },
        }

    def test_dry_run_no_apply_label(self):
        """apply_label must never be called when dry_run=True."""
        msg = self._make_msg(
            subject="50% off everything",
            sender="promo@retailer.com",
            age_days=60.0,
            labels=["CATEGORY_PROMOTIONS"],
        )

        service = MagicMock()
        service.users().messages().get().execute.return_value = msg

        label_map = {
            "Organizer/Promotions": "label_promo_id",
            "Organizer/Review Me": "label_review_id",
        }
        stats = {
            "processed": 0, "protected": 0,
            "categories": {
                "Important": 0, "Personal": 0, "Receipts": 0,
                "Promotions": 0, "Junk": 0,
            },
            "archived": 0, "deleted": 0, "review_me": 0, "errors": 0,
        }

        with patch("organizer.categorize.apply_label") as mock_apply, \
             patch("organizer.categorize.remove_from_inbox") as mock_arch, \
             patch("organizer.categorize.trash_message") as mock_trash:
            _process_one(
                service, "abc123", label_map, set(), stats, dry_run=True
            )

        mock_apply.assert_not_called()
        mock_arch.assert_not_called()
        mock_trash.assert_not_called()

    def test_dry_run_no_trash(self):
        """trash_message must never be called when dry_run=True."""
        # Old junk email that would normally be deleted
        msg = self._make_msg(
            subject="General update from service",
            sender="noreply@someservice.com",
            age_days=100.0,
            labels=[],
        )

        service = MagicMock()
        service.users().messages().get().execute.return_value = msg

        label_map = {
            "Organizer/Junk": "label_junk_id",
            "Organizer/Review Me": "label_review_id",
        }
        stats = {
            "processed": 0, "protected": 0,
            "categories": {
                "Important": 0, "Personal": 0, "Receipts": 0,
                "Promotions": 0, "Junk": 0,
            },
            "archived": 0, "deleted": 0, "review_me": 0, "errors": 0,
        }

        with patch("organizer.categorize.trash_message") as mock_trash, \
             patch("organizer.categorize.apply_label"), \
             patch("organizer.categorize.remove_from_inbox"):
            _process_one(
                service, "abc123", label_map, set(), stats, dry_run=True
            )

        mock_trash.assert_not_called()


class TestProtectionPaths(unittest.TestCase):
    """Verify protected emails never reach archive or delete code paths."""

    def _make_msg(
        self,
        subject: str,
        sender: str,
        snippet: str = "",
        age_days: float = 500.0,
    ) -> dict:
        """Build a minimal fake Gmail message dict."""
        ts_ms = int(
            (time.time() - age_days * 86400) * 1000
        )
        return {
            "id": "protected1",
            "snippet": snippet,
            "internalDate": str(ts_ms),
            "labelIds": [],
            "payload": {
                "headers": [
                    {"name": "Subject", "value": subject},
                    {"name": "From", "value": sender},
                    {"name": "List-Unsubscribe", "value": ""},
                ]
            },
        }

    def _run_process_one(self, msg: dict) -> tuple:
        """Run _process_one with mocked writes; return call counts."""
        service = MagicMock()
        service.users().messages().get().execute.return_value = msg

        label_map = {
            "Organizer/Saved": "label_saved_id",
            "Organizer/Junk": "label_junk_id",
            "Organizer/Promotions": "label_promo_id",
            "Organizer/Review Me": "label_review_id",
        }
        stats = {
            "processed": 0, "protected": 0,
            "categories": {
                "Important": 0, "Personal": 0, "Receipts": 0,
                "Promotions": 0, "Junk": 0,
            },
            "archived": 0, "deleted": 0, "review_me": 0, "errors": 0,
        }

        with patch("organizer.categorize.apply_label") as mock_apply, \
             patch("organizer.categorize.remove_from_inbox") as mock_arch, \
             patch("organizer.categorize.trash_message") as mock_trash:
            _process_one(
                service, "protected1", label_map, set(), stats,
                dry_run=False,
            )

        return mock_apply.call_args_list, mock_arch.call_count, \
            mock_trash.call_count, stats

    def test_masuk_domain_never_deleted(self):
        """Email from masuk.org → only Saved label, no archive/delete."""
        msg = self._make_msg(
            subject="Practice schedule",
            sender="coach@masuk.org",
            age_days=500.0,
        )
        apply_calls, arch_count, trash_count, stats = (
            self._run_process_one(msg)
        )

        self.assertEqual(trash_count, 0, "trash_message called on protected")
        self.assertEqual(arch_count, 0, "remove_from_inbox called on protected")
        self.assertEqual(stats["protected"], 1)
        # Only Organizer/Saved should have been applied
        applied_labels = [c.args[2] for c in apply_calls]
        self.assertEqual(applied_labels, ["Organizer/Saved"])

    def test_asu_domain_never_deleted(self):
        """Email from asu.edu → only Saved label, no archive/delete."""
        msg = self._make_msg(
            subject="Enrollment notice",
            sender="registrar@asu.edu",
            age_days=400.0,
        )
        apply_calls, arch_count, trash_count, stats = (
            self._run_process_one(msg)
        )

        self.assertEqual(trash_count, 0)
        self.assertEqual(arch_count, 0)
        applied_labels = [c.args[2] for c in apply_calls]
        self.assertEqual(applied_labels, ["Organizer/Saved"])

    def test_protected_keyword_never_deleted(self):
        """Email with 'tuition' keyword → Saved, never archived/deleted."""
        msg = self._make_msg(
            subject="Tuition payment confirmation",
            sender="billing@someuniversity.edu",
            age_days=400.0,
        )
        apply_calls, arch_count, trash_count, stats = (
            self._run_process_one(msg)
        )

        self.assertEqual(trash_count, 0)
        self.assertEqual(arch_count, 0)
        applied_labels = [c.args[2] for c in apply_calls]
        self.assertEqual(applied_labels, ["Organizer/Saved"])

    def test_monroe_ct_domain_never_deleted(self):
        """Email from monroe.ct.us → Saved, never archived/deleted."""
        msg = self._make_msg(
            subject="Town notice",
            sender="info@monroe.ct.us",
            age_days=300.0,
        )
        apply_calls, arch_count, trash_count, _ = (
            self._run_process_one(msg)
        )

        self.assertEqual(trash_count, 0)
        self.assertEqual(arch_count, 0)
        applied_labels = [c.args[2] for c in apply_calls]
        self.assertEqual(applied_labels, ["Organizer/Saved"])


class TestReviewMeGate(unittest.TestCase):
    """Verify the Review Me safety gate fires before archive/delete."""

    def test_important_signal_prevents_trash(self):
        """Old Junk email from a real person → Review Me, not trash."""
        age_days = 100.0
        ts_ms = int((time.time() - age_days * 86400) * 1000)
        msg = {
            "id": "test_msg",
            "snippet": "",
            "internalDate": str(ts_ms),
            "labelIds": ["UNREAD"],
            "payload": {
                "headers": [
                    # Real-person sender triggers importance signal
                    {"name": "From", "value": "alice.jones@gmail.com"},
                    {"name": "Subject", "value": "General update"},
                    {"name": "List-Unsubscribe", "value": ""},
                ]
            },
        }

        service = MagicMock()
        service.users().messages().get().execute.return_value = msg

        label_map = {
            "Organizer/Personal": "lbl_personal",
            "Organizer/Junk": "lbl_junk",
            "Organizer/Review Me": "lbl_review",
        }
        stats = {
            "processed": 0, "protected": 0,
            "categories": {
                "Important": 0, "Personal": 0, "Receipts": 0,
                "Promotions": 0, "Junk": 0,
            },
            "archived": 0, "deleted": 0, "review_me": 0, "errors": 0,
        }

        with patch("organizer.categorize.trash_message") as mock_trash, \
             patch("organizer.categorize.remove_from_inbox") as mock_arch, \
             patch("organizer.categorize.apply_label"):
            _process_one(
                service, "test_msg", label_map, set(), stats,
                dry_run=False,
            )

        mock_trash.assert_not_called()
        mock_arch.assert_not_called()


class TestGmailExecuteRetry(unittest.TestCase):
    """Verify gmail_execute retries on both HTTP and network errors."""

    def test_retries_on_429(self):
        """HTTP 429 should be retried up to retries-1 times."""
        resp = MagicMock()
        resp.status = 429
        request = MagicMock()
        request.execute.side_effect = [
            HttpError(resp=resp, content=b"rate limited"),
            HttpError(resp=resp, content=b"rate limited"),
            {"ok": True},
        ]

        with patch("organizer.utils.time.sleep"):
            result = gmail_execute(request, retries=5)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.execute.call_count, 3)

    def test_retries_on_network_error(self):
        """OSError (network drop) should be retried up to retries-1 times."""
        request = MagicMock()
        request.execute.side_effect = [
            ConnectionError("network unreachable"),
            ConnectionError("network unreachable"),
            {"ok": True},
        ]

        with patch("organizer.utils.time.sleep"):
            result = gmail_execute(request, retries=5)

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.execute.call_count, 3)

    def test_raises_after_max_retries(self):
        """Persistent network error raises after all retries exhausted."""
        request = MagicMock()
        request.execute.side_effect = ConnectionError("always down")

        with patch("organizer.utils.time.sleep"):
            with self.assertRaises(OSError):
                gmail_execute(request, retries=3)

        self.assertEqual(request.execute.call_count, 3)

    def test_non_retryable_http_error_raises_immediately(self):
        """HTTP 404 should raise immediately without retry."""
        resp = MagicMock()
        resp.status = 404
        request = MagicMock()
        request.execute.side_effect = HttpError(
            resp=resp, content=b"not found"
        )

        with patch("organizer.utils.time.sleep"):
            with self.assertRaises(HttpError):
                gmail_execute(request, retries=5)

        self.assertEqual(request.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()
