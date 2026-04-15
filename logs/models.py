from django.db import models


class ProductGroup(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(db_column='createdAt')
    updated_at = models.DateTimeField(db_column='updatedAt')

    class Meta:
        managed = False
        db_table = 'product_groups'

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    asin = models.CharField(max_length=50)
    name = models.CharField(max_length=255, blank=True, null=True)
    weight = models.FloatField(blank=True, null=True)
    bundle_qty = models.IntegerField(db_column='bundleQty', blank=True, null=True)
    title = models.CharField(max_length=500, blank=True, null=True)
    image_url = models.TextField(db_column='imageUrl', blank=True, null=True)
    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.DO_NOTHING,
        db_column='productGroupId',
        related_name='products',
    )
    is_archived = models.BooleanField(db_column='isArchived', default=False)

    class Meta:
        managed = False
        db_table = 'products'

    def __str__(self):
        return f'{self.asin} — {self.name or self.title or ""}'


class Barcode(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    code = models.CharField(max_length=100)
    product = models.ForeignKey(
        Product,
        on_delete=models.DO_NOTHING,
        db_column='productId',
        related_name='barcodes',
    )
    created_at = models.DateTimeField(db_column='createdAt')

    class Meta:
        managed = False
        db_table = 'barcodes'

    def __str__(self):
        return self.code


class SoStockedLog(models.Model):
    """Locally cached SoStocked log entry."""
    ss_id = models.BigIntegerField(unique=True, db_index=True)
    asin = models.CharField(max_length=20, db_index=True)
    area_name = models.CharField(max_length=100, blank=True, default='')
    created_at = models.CharField(max_length=30, db_index=True)
    order_number = models.CharField(max_length=100, blank=True, default='')
    param_diff = models.SmallIntegerField(default=0)
    real_diff = models.SmallIntegerField(default=0)
    old_qty = models.IntegerField(null=True)
    new_qty = models.IntegerField(null=True)
    user_name = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, default='')
    vendor_name = models.CharField(max_length=200, blank=True, default='')
    product_name = models.CharField(max_length=500, blank=True, default='')
    order_shipment_id = models.CharField(max_length=50, blank=True, default='')
    type_id = models.IntegerField(default=0, db_index=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['-created_at', 'asin']),
            models.Index(fields=['type_id', '-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.ss_id} {self.asin} {self.created_at}'
