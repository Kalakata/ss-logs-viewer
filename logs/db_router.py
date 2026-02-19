class WmsRouter:
    """Route ProductGroup and Product reads to the 'wms' database.
    Block all writes and migrations against 'wms'."""

    wms_models = {'productgroup', 'product', 'barcode'}

    def db_for_read(self, model, **hints):
        if model._meta.model_name in self.wms_models:
            return 'wms'
        return None

    def db_for_write(self, model, **hints):
        if model._meta.model_name in self.wms_models:
            return False
        return None

    def allow_relation(self, obj1, obj2, **hints):
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if db == 'wms':
            return False
        if model_name in self.wms_models:
            return False
        return None
