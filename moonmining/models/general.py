"""General models."""

from django.db import models


class General(models.Model):
    """Meta model for global app permissions"""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access the moonmining app"),
            ("extractions_access", "Can access extractions and view owned moons"),
            ("reports_access", "Can access reports"),
            ("view_all_moons", "Can view all known moons"),
            ("upload_moon_scan", "Can upload moon scans"),
            ("add_refinery_owner", "Can add refinery owner"),
            ("view_moon_ledgers", "Can view moon ledgers"),
        )
