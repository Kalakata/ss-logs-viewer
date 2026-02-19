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
