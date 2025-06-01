from cheques.models import PaymentInstrumentType, PaymentInstrument


class InstrumentPolicy:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Initialize the instance (this will only run once)
        if not hasattr(self, 'initialized'):
            print("Singleton instance initialized!")
            self.initialized = True

# Get instances of the singleton class
# instance1 = PaymentInstrument()
# instance2 = PaymentInstrument()

# print(instance1 is instance2) # Output: True

class PaymentInstrumentPolicy:
    _payment_instrument_types = None
    _payment_instruments = None

    @classmethod
    def get_payment_instrument_types(cls):
        if cls._payment_instrument_types is None:
            cls._payment_instrument_types = PaymentInstrumentType.objects.all()
        return cls._payment_instrument_types

    @classmethod
    def get_payment_instruments(cls):
        if cls._payment_instruments is None:
            cls._payment_instruments = PaymentInstrument.objects.all()
        return cls._payment_instruments

    @classmethod
    def get_instrument_auto_number_by_id(cls, instrument_id):
        if not cls._payment_instruments:
            for instrument in cls.get_payment_instruments():
                if instrument.id == instrument_id:
                    ins_type=  instrument.instrument_type
                    exit
            for instrumentType in cls.get_payment_instrument_types():
                if instrumentType.id == ins_type:
                    return instrumentType.auto_number
                
        return None
    
    @classmethod
    def get_instrument_auto_number_by_type_id(cls, ins_type_id):

        for instrumentType in cls.get_payment_instrument_types():
            if instrumentType.id == ins_type_id:
                return instrumentType.auto_number
                
        return None