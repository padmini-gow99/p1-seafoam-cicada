
from sqlmodel import SQLModel, Field, Session, create_engine, select

DATABASE_URL = "sqlite:///orders.db"   # SQLite DB file
engine = create_engine(DATABASE_URL, echo=True)


class Order(SQLModel, table=True):
    id: str = Field(primary_key=True)
    product_name: str
    status: str
    price: float
    customer_name: str

def init_db():
    SQLModel.metadata.create_all(engine)

def get_order_by_id(order_id: str):
    with Session(engine) as session:
        statement = select(Order).where(Order.id == order_id)
        return session.exec(statement).first()

def update_order_status(order_id: str, new_status: str):
    with Session(engine) as session:
        order = session.get(Order, order_id)
        if not order:
            return None

        order.status = new_status
        session.add(order)
        session.commit()
        session.refresh(order)
        return order


def get_orders_by_customer(name: str):
    with Session(engine) as session:
        statement = select(Order).where(Order.customer_name == name)
        return session.exec(statement).all()


def cancel_order(order_id: str):
    return update_order_status(order_id, "Canceled")


def return_order(order_id: str):
    return update_order_status(order_id, "Return Requested")
