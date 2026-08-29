from django.db import migrations, models
from django.db.models import Count, Q


def reject_duplicate_gateway_trade_numbers(apps, schema_editor):
    PaymentTransaction = apps.get_model('payments', 'PaymentTransaction')
    duplicates = list(
        PaymentTransaction.objects.exclude(trade_no='')
        .values('gateway', 'trade_no')
        .annotate(duplicate_count=Count('id'))
        .filter(duplicate_count__gt=1)
        .order_by('gateway', 'trade_no')
    )
    if duplicates:
        details = ', '.join(
            f"{row['gateway']}:{row['trade_no']} ({row['duplicate_count']} rows)"
            for row in duplicates
        )
        raise RuntimeError(
            'Cannot add payments gateway/trade_no uniqueness constraint; '
            f'existing non-empty duplicates must be resolved first: {details}'
        )


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_refundrequest'),
    ]

    operations = [
        migrations.RunPython(
            reject_duplicate_gateway_trade_numbers,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='paymenttransaction',
            constraint=models.UniqueConstraint(
                fields=('gateway', 'trade_no'),
                condition=~Q(trade_no=''),
                name='uniq_payment_gateway_trade_no_nonempty',
            ),
        ),
    ]
