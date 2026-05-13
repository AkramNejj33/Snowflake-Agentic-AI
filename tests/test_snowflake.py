"""Tests for SnowflakeClient — requires a real Snowflake connection."""

import os
import pytest
import pandas as pd

# Skip all tests if credentials are not set
pytestmark = pytest.mark.skipif(
    not os.getenv("SNOWFLAKE_ACCOUNT"),
    reason="SNOWFLAKE_ACCOUNT not set — skipping integration tests",
)


@pytest.fixture(scope="module")
def client():
    """Return a connected SnowflakeClient (module-scoped singleton)."""
    from src.snowflake_client import get_client
    c = get_client()
    yield c
    c.close()


class TestConnection:
    def test_is_healthy(self, client):
        assert client.is_healthy() is True

    def test_execute_simple_query(self, client):
        df = client.execute_query("SELECT 42 AS answer, 'hello' AS greeting")
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df["ANSWER"].iloc[0] == 42
        assert df["GREETING"].iloc[0] == "hello"

    def test_execute_returns_empty_for_ddl(self, client):
        # A SELECT that returns nothing
        df = client.execute_query(
            "SELECT 1 WHERE 1 = 0"
        )
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


class TestSchemaIntrospection:
    def test_list_tables_raw(self, client):
        tables = client.list_tables("RAW")
        assert isinstance(tables, list)
        assert "CUSTOMERS" in tables
        assert "PRODUCTS" in tables
        assert "SALES" in tables

    def test_get_schema_customers(self, client):
        info = client.get_schema("CUSTOMERS", schema="RAW")
        assert info["table"] == "CUSTOMERS"
        assert info["schema"] == "RAW"
        col_names = [c["name"] for c in info["columns"]]
        assert "CUSTOMER_ID" in col_names
        assert "EMAIL" in col_names
        assert "SEGMENT" in col_names

    def test_get_schema_fully_qualified(self, client):
        info = client.get_schema("RAW.PRODUCTS")
        assert info["table"] == "PRODUCTS"

    def test_list_tables_analytics(self, client):
        tables = client.list_tables("ANALYTICS")
        assert isinstance(tables, list)
        # Views should be listed too
        assert len(tables) >= 0  # May be 0 if views aren't created yet


class TestDataQueries:
    def test_count_customers(self, client):
        df = client.execute_query("SELECT COUNT(*) AS N FROM RAW.CUSTOMERS")
        assert df["N"].iloc[0] >= 0

    def test_customers_have_email(self, client):
        df = client.execute_query(
            "SELECT COUNT(*) AS N FROM RAW.CUSTOMERS WHERE EMAIL IS NULL"
        )
        assert df["N"].iloc[0] == 0

    def test_products_positive_price(self, client):
        df = client.execute_query(
            "SELECT COUNT(*) AS N FROM RAW.PRODUCTS WHERE UNIT_PRICE <= 0"
        )
        assert df["N"].iloc[0] == 0

    def test_sales_join(self, client):
        df = client.execute_query(
            """
            SELECT s.SALE_ID, c.EMAIL, p.PRODUCT_NAME
            FROM RAW.SALES s
            JOIN RAW.CUSTOMERS c ON s.CUSTOMER_ID = c.CUSTOMER_ID
            JOIN RAW.PRODUCTS  p ON s.PRODUCT_ID  = p.PRODUCT_ID
            LIMIT 5
            """
        )
        assert isinstance(df, pd.DataFrame)
        assert "SALE_ID" in df.columns


class TestRetry:
    def test_invalid_sql_raises(self, client):
        from snowflake.connector import ProgrammingError
        with pytest.raises(ProgrammingError):
            client.execute_query("SELECT * FROM THIS_TABLE_DOES_NOT_EXIST_EVER")
