"""Unit tests for organizer.rules classification and scoring logic."""

import unittest

from organizer.rules import (
    classify_email,
    is_important_signal,
    is_protected,
    score_priority,
)


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


if __name__ == "__main__":
    unittest.main()
