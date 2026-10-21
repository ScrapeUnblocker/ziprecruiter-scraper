"""Errors raised by the scraper."""

from __future__ import annotations


class ZipRecruiterError(Exception):
    """Base class for scraper errors."""


class ParseError(ZipRecruiterError):
    """The page came back without the data ZipRecruiter normally puts in it."""


class NotFoundError(ZipRecruiterError, LookupError):
    """ZipRecruiter has no such job (the job page answers HTTP 404)."""
