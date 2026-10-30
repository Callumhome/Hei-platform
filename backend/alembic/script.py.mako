"""${message}"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ''}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${ up_revision_ops if up_revision_ops else 'pass' }


def downgrade() -> None:
    ${ down_revision_ops if down_revision_ops else 'pass' }
