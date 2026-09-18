"""
api/auth/roles.py
=================
Roles and the permission matrix. A route declares the *permission* it needs
(via require_permission in deps.py); any role that holds that permission passes.

Keep this file as the single source of truth for "who can do what". Adding a new
capability = add a Permission and grant it to the right roles here — routes and
frontend read from the same matrix.
"""

from enum import Enum


class Role(str, Enum):
    ADMIN            = "admin"
    SALES_MANAGER    = "sales_manager"
    SALES_REP        = "sales_rep"
    MARKETING        = "marketing_analyst"
    DATA_ANALYST     = "data_analyst"
    VIEWER           = "viewer"          # executives / read-only


class Permission(str, Enum):
    # prospects
    PROSPECT_VIEW_ALL     = "prospect:view_all"      # see the whole DB
    PROSPECT_VIEW_ASSIGNED = "prospect:view_assigned" # see only own assignments
    PROSPECT_VIEW_CONTACT = "prospect:view_contact"   # see phone/email per lead
    PROSPECT_ASSIGN       = "prospect:assign"         # assign leads to reps
    PROSPECT_UPDATE_STATUS = "prospect:update_status" # log calls / change status
    PROSPECT_EXPORT       = "prospect:export"         # export lists

    # segments & campaigns (marketing)
    SEGMENT_VIEW          = "segment:view"
    CAMPAIGN_PLAN         = "campaign:plan"           # allocate budget / build campaigns

    # pipeline & data quality
    PIPELINE_RUN          = "pipeline:run"
    TAXONOMY_EDIT         = "taxonomy:edit"           # edit taxonomy / validated examples
    MERGE_REVIEW          = "merge:review"            # resolve borderline merge pairs

    # administration
    USER_MANAGE           = "user:manage"
    CONFIG_EDIT           = "config:edit"             # scoring weights, thresholds
    AUDIT_VIEW            = "audit:view"


# Role → set of permissions. Least-privilege by design.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: set(Permission),  # everything

    Role.SALES_MANAGER: {
        Permission.PROSPECT_VIEW_ALL,
        Permission.PROSPECT_VIEW_CONTACT,
        Permission.PROSPECT_ASSIGN,
        Permission.PROSPECT_UPDATE_STATUS,
        Permission.PROSPECT_EXPORT,
        Permission.SEGMENT_VIEW,
    },

    Role.SALES_REP: {
        Permission.PROSPECT_VIEW_ASSIGNED,
        Permission.PROSPECT_VIEW_CONTACT,
        Permission.PROSPECT_UPDATE_STATUS,
    },

    Role.MARKETING: {
        Permission.SEGMENT_VIEW,
        Permission.CAMPAIGN_PLAN,
        Permission.PROSPECT_VIEW_ALL,   # aggregate view; contact details withheld
        Permission.PROSPECT_EXPORT,
    },

    Role.DATA_ANALYST: {
        Permission.PROSPECT_VIEW_ALL,
        Permission.PIPELINE_RUN,
        Permission.TAXONOMY_EDIT,
        Permission.MERGE_REVIEW,
        Permission.SEGMENT_VIEW,
    },

    Role.VIEWER: {
        Permission.PROSPECT_VIEW_ALL,   # read-only; no contact, no writes
        Permission.SEGMENT_VIEW,
    },
}


def permissions_for(role: Role) -> set[Permission]:
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in permissions_for(role)
