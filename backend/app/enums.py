"""Domain enumerations. Stored as plain strings in the database for portability."""

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"                                # system administrator (cannot act on instruments)
    COMPETENT_AUTHORITY = "COMPETENT_AUTHORITY"    # Member Secretary: approves release of deposits
    RB_HEAD = "RB_HEAD"                            # head of the Regulation Bureau
    RB_OFFICER = "RB_OFFICER"                      # dealing officer: scrutiny and verification
    ACCOUNTS = "ACCOUNTS"                          # Finance & Accounts: lien release and refund execution
    REGIONAL_OFFICER = "REGIONAL_OFFICER"          # read view of institutions in the region
    AUDITOR = "AUDITOR"                            # internal audit / vigilance: read-only, verifies integrity
    INSTITUTION = "INSTITUTION"                    # an institution's authorised user


STAFF_ROLES = (Role.COMPETENT_AUTHORITY, Role.RB_HEAD, Role.RB_OFFICER, Role.ACCOUNTS, Role.REGIONAL_OFFICER,
               Role.AUDITOR, Role.ADMIN)


class UnitType(StrEnum):
    BUREAU = "BUREAU"
    FINANCE = "FINANCE"
    REGIONAL_OFFICE = "REGIONAL_OFFICE"
    MANAGEMENT = "MANAGEMENT"


class InstrumentKind(StrEnum):
    FDR = "FDR"                            # fixed deposit receipt pledged to AICTE
    SECURITY_DEPOSIT = "SECURITY_DEPOSIT"  # deposit paid into AICTE's account (e-receipt / challan)


class Purpose(StrEnum):
    NEW_INSTITUTION = "NEW_INSTITUTION"
    NEW_PROGRAMME = "NEW_PROGRAMME"
    INTAKE_INCREASE = "INTAKE_INCREASE"
    OTHER = "OTHER"


class Status(StrEnum):
    SUBMITTED = "SUBMITTED"                # received, awaiting scrutiny
    UNDER_SCRUTINY = "UNDER_SCRUTINY"      # officer reviewing, bank verification in progress
    DISCREPANCY = "DISCREPANCY"            # open discrepancies, institution asked to rectify
    ACTIVE = "ACTIVE"                      # verified and held
    EXPIRING = "EXPIRING"                  # active, maturity within the reminder window
    MATURED = "MATURED"                    # past maturity, renewal or replacement awaited
    RENEWED = "RENEWED"                    # replaced by a verified successor instrument (closed)
    RELEASE_REQUESTED = "RELEASE_REQUESTED"
    RELEASED = "RELEASED"                  # lien discharged / refunded (closed)
    REJECTED = "REJECTED"                  # not accepted (closed)


OPEN_STATUSES = (Status.SUBMITTED, Status.UNDER_SCRUTINY, Status.DISCREPANCY, Status.ACTIVE, Status.EXPIRING,
                 Status.MATURED, Status.RELEASE_REQUESTED)
HELD_STATUSES = (Status.ACTIVE, Status.EXPIRING, Status.MATURED, Status.RELEASE_REQUESTED)
PENDING_SCRUTINY = (Status.SUBMITTED, Status.UNDER_SCRUTINY, Status.DISCREPANCY)
CLOSED_STATUSES = (Status.RENEWED, Status.RELEASED, Status.REJECTED)


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    REQUESTED = "REQUESTED"    # asked the bank (letter or gateway), awaiting reply
    CONFIRMED = "CONFIRMED"    # bank confirmed every field
    MISMATCH = "MISMATCH"      # bank reply differs from what was declared
    NOT_FOUND = "NOT_FOUND"    # bank has no such instrument


class VerificationChannel(StrEnum):
    GATEWAY = "GATEWAY"        # bank's online verification service (simulated connector in the demo)
    LETTER = "LETTER"          # verification letter to the branch, reply recorded by the officer
    MANUAL = "MANUAL"          # officer recorded a confirmation received another way


class Source(StrEnum):
    """Where a value came from. The portal never mixes these up."""

    DECLARED = "DECLARED"      # typed by the institution
    DOCUMENT = "DOCUMENT"      # read from the uploaded FDR document
    BANK = "BANK"              # confirmed by the issuing bank


class DiscrepancyStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"      # fixed (rectified instrument or corrected record)
    WAIVED = "WAIVED"          # accepted by the RB head with a recorded reason


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_RANK = {s: i for i, s in enumerate(Severity)}


class ReleaseStatus(StrEnum):
    REQUESTED = "REQUESTED"        # institution (or officer) asked for release
    RECOMMENDED = "RECOMMENDED"    # dealing officer checked conditions and recommended
    APPROVED = "APPROVED"          # competent authority approved
    EXECUTED = "EXECUTED"          # accounts discharged the lien / refunded
    REJECTED = "REJECTED"


class ReleaseReason(StrEnum):
    REPLACED = "REPLACED"                  # a newer instrument has taken its place
    CLOSURE = "CLOSURE"                    # institution / programme closed with no liabilities
    APPROVAL_NOT_GRANTED = "APPROVAL_NOT_GRANTED"
    PERIOD_COMPLETED = "PERIOD_COMPLETED"  # the prescribed holding period is over
    OTHER = "OTHER"


class EventType(StrEnum):
    SUBMITTED = "SUBMITTED"
    DOCUMENT_ATTACHED = "DOCUMENT_ATTACHED"
    DOCUMENT_READ = "DOCUMENT_READ"
    CHECKS_RUN = "CHECKS_RUN"
    ASSIGNED = "ASSIGNED"
    SCRUTINY_STARTED = "SCRUTINY_STARTED"
    OBSERVATION = "OBSERVATION"
    BANK_VERIFICATION_REQUESTED = "BANK_VERIFICATION_REQUESTED"
    BANK_VERIFIED = "BANK_VERIFIED"
    DISCREPANCY_RAISED = "DISCREPANCY_RAISED"
    DISCREPANCY_RESOLVED = "DISCREPANCY_RESOLVED"
    DISCREPANCY_WAIVED = "DISCREPANCY_WAIVED"
    RECTIFICATION_SUBMITTED = "RECTIFICATION_SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    REMINDER_SENT = "REMINDER_SENT"
    EXPIRING = "EXPIRING"
    MATURED = "MATURED"
    ESCALATED = "ESCALATED"
    RENEWAL_SUBMITTED = "RENEWAL_SUBMITTED"
    RENEWED = "RENEWED"
    RELEASE_REQUESTED = "RELEASE_REQUESTED"
    RELEASE_RECOMMENDED = "RELEASE_RECOMMENDED"
    RELEASE_APPROVED = "RELEASE_APPROVED"
    RELEASE_REJECTED = "RELEASE_REJECTED"
    RELEASED = "RELEASED"
    LETTER_ISSUED = "LETTER_ISSUED"
    FIELD_CORRECTED = "FIELD_CORRECTED"


class AlertKind(StrEnum):
    MATURITY_DUE = "MATURITY_DUE"            # maturity within a reminder window
    MATURED_UNRENEWED = "MATURED_UNRENEWED"  # matured and no successor yet
    VERIFICATION_PENDING = "VERIFICATION_PENDING"
    DISCREPANCY = "DISCREPANCY"
    FRAUD_SIGNAL = "FRAUD_SIGNAL"            # reused FDR or document, premature closure at the bank
    RELEASE_PENDING = "RELEASE_PENDING"
    ESCALATION = "ESCALATION"
    RENEWAL_RISK = "RENEWAL_RISK"            # predicted to renew late
    INTEGRITY = "INTEGRITY"                  # ledger verification failed


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class LetterKind(StrEnum):
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"            # to the institution, on submission
    BANK_VERIFICATION = "BANK_VERIFICATION"        # to the branch, asking it to confirm the FDR
    RECTIFICATION = "RECTIFICATION"                # to the institution, listing discrepancies
    LIEN_RELEASE = "LIEN_RELEASE"                  # to the branch, discharging AICTE's lien


class NotificationChannel(StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"


class MatchStatus(StrEnum):
    """Outcome of matching a name (e.g. the depositor on an FDR) against the institution master."""

    AUTO = "AUTO"
    CONFIRMED = "CONFIRMED"
    MANUAL = "MANUAL"
    SUGGESTED = "SUGGESTED"
    UNMATCHED = "UNMATCHED"
