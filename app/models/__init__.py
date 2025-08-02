# app/models/__init__.py

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Importar todos los modelos para que create_all() los vea
from .gas_station import GasStation
from .gas_price import GasPrice
from .user_report import UserPriceReport
from .review import GasStationReview