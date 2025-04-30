from lib import find_base_tables,find_cte_dependencies,find_table_relationship
from lib import find_source_target_table,has_table,find_parseable_ast,find_physical_column
from sqlglot import parse_one,parse


def test_find_base_tables():
    sql = """

    WITH
    cte1 AS (
        SELECT a, b
        FROM table1
    ),
    cte2 AS (
        SELECT c
        FROM table2
    ),
    cte3 AS (
        SELECT a, c
        FROM cte1
        JOIN cte2 ON cte1.b = cte2.c
    ),
    final_result AS (
        SELECT cte1.a, cte3.c
        FROM cte1
        JOIN cte3 ON cte1.a = cte3.a
    )
    SELECT *
    FROM final_result;

    """

    tables = find_base_tables(parse_one(sql=sql))

    assert "table1" in tables
    assert "table2" in tables

def test_find_cte_dependencies():

    sql = """

    WITH
    cte1 AS (
        SELECT a, b
        FROM table1
    ),
    cte2 AS (
        SELECT c
        FROM table2
    ),
    cte3 AS (
        SELECT a, c
        FROM cte1
        JOIN cte2 ON cte1.b = cte2.c
    ),
    final_result AS (
        SELECT cte1.a, cte3.c
        FROM cte1
        JOIN cte3 ON cte1.a = cte3.a
    )
    SELECT *
    FROM final_result;

    """

    dependencies = find_cte_dependencies(parse_one(sql))

    assert "cte1" in dependencies
    assert "cte2" in dependencies
    assert "cte3" in dependencies
    assert "final_result" in dependencies

    assert "table1" in dependencies["cte1"]
    
    assert "table2" in dependencies["cte2"]

    assert "cte1" in dependencies["cte3"]
    assert "cte2" in dependencies["cte3"]

    assert "cte1" in dependencies["final_result"]
    assert "cte3" in dependencies["final_result"]
  
def test_find_table_relationship():
    sql = """
    SELECT * 
    FROM table1
    INNER JOIN table2 AS t2
    ON table1.id = t2.id
    INNER JOIN table3
    ON table1.id = table3.id

    """

    ast = parse_one(sql=sql)

    relationship = find_table_relationship(ast)

    for x in relationship:
        assert x[0]=="table1" and (x[1]=="table2" or x[1]=="table3")
    
def test_find_source_target_table_single_select_into():

    sql = """

    SELECT foo.id
    INTO bar
    FROM foo
    INNER JOIN product
    ON foo.id = product.id

    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==2
    assert "foo" in source
    assert "product" in source

    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_cte_select_into():

    sql = """

    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    SELECT foo.id
    INTO bar
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    INNER JOIN cat
    ON foo.id = cat.id

    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==3
    assert "foo" in source
    assert "product" in source
    assert "dog" in source

    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_single_insert_into():

    sql = """
    INSERT INTO bar(id)
    SELECT foo.id
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==2
    assert "foo" in source
    assert "product" in source


    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_cte_insert_into():

    sql = """
    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    INSERT INTO bar(id)
    SELECT foo.id
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    INNER JOIN cat
    ON foo.id = cat.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==3
    assert "foo" in source
    assert "product" in source
    assert "dog" in source


    assert len(target)==1
    assert "bar" in target


def test_find_source_target_table_single_insert():

    sql = """
    INSERT bar(id)
    SELECT foo.id
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==2
    assert "foo" in source
    assert "product" in source


    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_cte_insert_():

    sql = """
    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    INSERT bar(id)
    SELECT foo.id
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    INNER JOIN cat
    ON foo.id = cat.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    
    assert len(source)==3
    assert "foo" in source
    assert "product" in source
    assert "dog" in source


    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_single_update():

    sql = """

    UPDATE bar
    SET id = 10 
    FROM bar
    INNER JOIN product
    ON foo.id = product.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==2
    assert "bar" in source
    assert "product" in source

    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_cte_update():

    sql = """

    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    UPDATE bar
    SET id = 10 
    FROM bar
    INNER JOIN cat
    ON foo.id = cat.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==2
    assert "bar" in source
    assert "dog" in source

    assert len(target)==1
    assert "bar" in target

def test_find_source_target_table_single_delete():

    sql = """

    DELETE
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    WHERE id = 10
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==2
    assert "foo" in source
    assert "product" in source

    assert len(target)==1
    assert "foo" in target

def test_find_source_target_table_cte_delete():

    sql = """

    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    DELETE
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    INNER JOIN cat
    ON foo.id = cat.id
    WHERE id = 10
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==3
    assert "foo" in source
    assert "product" in source
    assert "dog" in source


    assert len(target)==1
    assert "foo" in target


def test_find_source_target_table_drop():

    sql = """

    DROP TABLE foo;

    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==1
    assert "foo" in source

    assert len(target)==0

def test_has_no_table():
    
    sql = """

    DECLARE @a int = 10;

    """

    ast = parse_one(sql=sql,dialect="tsql")

    assert not has_table(ast)


def test_has_table():

    sql = """

    SELECT * 
    FROM foo

    """

    ast = parse_one(sql=sql,dialect="tsql")

    assert has_table(ast)

def test_find_parseable_ast():

    sql = """

    DECLARE @a int = 10;

    WITH cat AS
    (
        SELECT id 
        FROM dog
    )
    DELETE
    FROM foo
    INNER JOIN product
    ON foo.id = product.id
    INNER JOIN cat
    ON foo.id = cat.id
    WHERE id = 10
    """

    asts = find_parseable_ast(parse(sql=sql,dialect="tsql"))

    assert len(asts)==1

def test_find_source_target_table_cte_delete_condition():

    sql = """

        WITH cat AS
        (
            SELECT id 
            FROM dog
        )
        DELETE
        FROM foo
        INNER JOIN product
        ON foo.id = product.id
        INNER JOIN cat
        ON foo.id = cat.id
        WHERE id = 10

    """

    asts = parse(sql=sql,dialect="tsql")

    ast = find_parseable_ast(asts=asts)[0]

    (source,target) = find_source_target_table(ast=ast)
    
    assert len(source)==3
    assert "foo" in source
    assert "product" in source
    assert "dog" in source

    assert len(target)==1
    assert "foo" in target


def test_string_replace(text):
    return str.replace(text," ","")

def test_find_source_target_table_create_table():
    sql  = """

    CREATE TABLE foo
    WITH (
        DISTRIBUTION = ROUND_ROBIN,
        HEAP
    )
    AS
    SELECT Id
    FROM bar
    INNER JOIN product
    ON bar.id = product.id

    """

    ast = parse_one(sql,dialect="tsql")

    (source,target) = find_source_target_table(ast=ast)

    assert len(source)==2
    assert "bar" in source
    assert "product" in source


    assert len(target)==1
    assert "foo" in target

def test_find_source_target_table_single_insert_into_with_database_schema():

    sql = """
    INSERT INTO hello.bar(id)
    SELECT foo.id
    FROM db.s1.foo
    INNER JOIN s2.product
    ON foo.id = product.id
    """

    ast = parse_one(sql=sql)

    (source,target) = find_source_target_table(ast=ast)
    
    assert len(source)==2
    assert "db.s1.foo" in source
    assert "s2.product" in source


    assert len(target)==1
    assert "hello.bar" in target

def test_physical_column():
    sql = """

    WITH SalesSummary AS (
        SELECT p.Product_Name, SUM(s.Quantity) AS Total_Sales
        FROM Products p
        JOIN Sales s ON p.Product_ID = s.Product_ID
        WHERE s.Sale_Date BETWEEN TO_DATE('2021-01-01', 'YYYY-MM-DD') AND TO_DATE('2021-12-31', 'YYYY-MM-DD')
        GROUP BY p.Product_Name
    )
    SELECT ss.Product_Name, ss.Total_Sales, c.Category_Name
    FROM SalesSummary ss
    JOIN Categories c ON ss.Product_Name = c.Product_Name
    ORDER BY ss.Total_Sales DESC;
    """

    ast = parse_one(sql=sql)

    expected_dict = dict()
    expected_dict["Products"] = ["Product_Name","Product_ID","Product_Name"]
    expected_dict["Sales"] = ["Quantity","Product_ID","Sale_Date"]
    expected_dict["Categories"] = ["Category_Name","Product_Name"]

    tuples = find_physical_column(ast)

    for item in tuples:

        first_item = item[0]

        second_item = item[1]

        assert first_item in expected_dict
        assert second_item in expected_dict[first_item]




def tests():
    test_find_base_tables()
    test_find_cte_dependencies()
    test_find_table_relationship()
    test_find_source_target_table_single_select_into()
    test_find_source_target_table_cte_select_into()
    test_find_source_target_table_single_insert_into()
    test_find_source_target_table_single_insert()
    test_find_source_target_table_single_insert()
    test_find_source_target_table_cte_insert_into()
    test_find_source_target_table_single_update()
    test_find_source_target_table_cte_update()
    test_find_source_target_table_single_delete()
    test_find_source_target_table_cte_delete()
    test_find_source_target_table_drop()
    test_find_source_target_table_cte_delete_condition()
    test_find_source_target_table_create_table()

    test_has_table()
    test_has_no_table()

    test_find_parseable_ast()

    test_find_source_target_table_single_insert_into_with_database_schema()

    test_physical_column()

if __name__=="__main__":
    tests()
