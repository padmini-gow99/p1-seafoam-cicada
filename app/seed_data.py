
from app.database import Order, engine, init_db
from sqlmodel import Session

init_db()   

def seed_orders():
    sample_orders = [
        Order(
            id="ORD1001",
            product_name="iPhone 15 Pro",
            status="Delivered",
            price=1299.99,
            customer_name="Padmini Bolem"
        ),
        Order(
            id="ORD1002",
            product_name="Samsung Galaxy S24",
            status="Shipped",
            price=999.99,
            customer_name="John Doe"
        ),
        Order(
            id="ORD1003",
            product_name="MacBook Air M3",
            status="Processing",
            price=1499.00,
            customer_name="Mary Jane"
        ),
    ]

    with Session(engine) as session:
        for order in sample_orders:
            existing = session.get(Order, order.id)
            if not existing:
                session.add(order)

        session.commit()
        print("✅ Orders added successfully!")


if __name__ == "__main__":
    seed_orders()
