from lib import find_base_tables,find_cte_dependencies,find_table_relationship
from lib import find_source_target_table,has_table,find_parseable_ast,find_physical_column
from lib import Metadata,MetadataObject,find_column_lineage
from sqlglot import parse_one,parse,exp
from typing import List


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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]
    
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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]
    
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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]
    
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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]
    
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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

def test_has_table_merge():
    
    sql = """

    MERGE INTO target_table 
    USING source_table
    ON target_table.id = source_table.id
    WHEN MATCHED THEN 
    UPDATE SET target_table.value = source_table.value
    WHEN NOT MATCHED THEN 
    INSERT (id,value) VALUES(source_table.id,source_table.value)

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

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

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==2
    assert "db.s1.foo" in source
    assert "s2.product" in source


    assert len(target)==1
    assert "hello.bar" in target

def test_find_source_target_table_if():
    sql = """

    IF(1=1)
    BEGIN
        SELECT id
        FROM cat
    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

def test_find_source_target_table_if_else():

    sql = """

    IF(1=1)
    BEGIN
        SELECT id
        FROM cat
    END
    ELSE
    BEGIN
        SELECT id
        FROM dog
    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)

    assert len(output)==2

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

    (source,target) = output[1]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==0


def test_find_source_target_table_if_elseif():

    sql = """

    IF(1=1)
    BEGIN
        SELECT id
        FROM cat
    END
    ELSE IF(1=2)
    BEGIN
        SELECT id
        FROM dog
    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)

    assert len(output)==2

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

    (source,target) = output[1]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==0


def test_find_source_target_table_if_elseif_else():

    sql = """

    IF(1=1)
    BEGIN
        SELECT id
        FROM cat
    END
    ELSE IF(1=2)
    BEGIN
        SELECT id
        FROM dog
    END
    ELSE
    BEGIN
        SELECT id
        FROM apple
    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)

    assert len(output)==3

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

    (source,target) = output[1]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==0

    (source,target) = output[2]

    assert len(source)==1
    assert "apple" in source
    assert len(target)==0

def test_find_source_target_table_nested_if():

    # if nested-if statement the semi-comma(;) is important to correctly parse the ast true
    # without semicomma , we will get parser error

    sql = """

    IF(1=1)
    BEGIN
        SELECT id
        FROM cat;

        IF(2=3)
        BEGIN
            SELECT id
            FROM orange;
        END

    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
    
    assert len(output)==2

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

    (source,target) = output[1]

    assert len(source)==1
    assert "orange" in source
    assert len(target)==0


def test_find_source_target_table_while():
    sql = """

    WHILE(1=1)
    BEGIN
        SELECT id
        FROM cat
    END

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
        
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==0

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

def test_find_source_target_table_merge():

    sql = """

    MERGE INTO target_table 
    USING source_table
    ON target_table.id = source_table.id
    WHEN MATCHED THEN 
    UPDATE SET target_table.value = source_table.value
    WHEN NOT MATCHED THEN 
    INSERT (id,value) VALUES(source_table.id,source_table.value)

    """
    
    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
        
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "source_table" in source
    assert len(target)==1
    assert "target_table" in target

def test_find_source_target_table_merge_alias():

    sql = """

    MERGE INTO target_table AS target
    USING source_table AS source
    ON target.id = source.id
    WHEN MATCHED THEN 
    UPDATE SET target.value = source.value
    WHEN NOT MATCHED THEN 
    INSERT (id,value) VALUES(source.id,source.value)

    """
    
    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
        
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "source_table" in source
    assert len(target)==1
    assert "target_table" in target

def test_find_source_target_table_merge_cte():

    sql = """

    WITH source_table AS 
    (
        SELECT id,
        value
        FROM dog
    )
    MERGE INTO target_table 
    USING source_table
    ON target_table.id = source_table.id
    WHEN MATCHED THEN 
    UPDATE SET target_table.value = source_table.value
    WHEN NOT MATCHED THEN 
    INSERT (id,value) VALUES(source_table.id,source_table.value)

    """
    
    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
        
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==1
    assert "target_table" in target

def test_find_source_target_table_try():

    sql = """

    BEGIN TRY

        INSERT INTO dog(id)
        SELECT id 
        FROM cat;

    END TRY

    """

    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
        
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==1
    assert "dog" in target

def test_find_source_target_table_try_catch():

    sql = """

    BEGIN TRY

        INSERT INTO dog(id)
        SELECT id 
        FROM cat;

    END TRY

    BEGIN CATCH

        INSERT INTO people(id)
        SELECT id 
        FROM dog;

    END CATCH
    """

    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
    
    assert len(output)==2

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==1
    assert "dog" in target

    (source,target) = output[1]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==1
    assert "people" in target

def test_find_source_target_table_try_catch_multi_statement():

    sql = """

    BEGIN TRY

        INSERT INTO dog(id)
        SELECT id 
        FROM cat;

        INSERT INTO fish(id)
        SELECT id
        FROM dog;

    END TRY

    BEGIN CATCH

        INSERT INTO people(id)
        SELECT id 
        FROM dog;

        INSERT INTO orange(id)
        SELECT id
        FROM apple;

    END CATCH
    """

    ast = parse_one(sql,dialect="tsql")

    output = find_source_target_table(ast=ast)
    
    assert len(output)==4

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==1
    assert "dog" in target

    (source,target) = output[1]
    
    assert len(source)==1
    assert "dog" in source
    assert len(target)==1
    assert "fish" in target

    (source,target) = output[2]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==1
    assert "people" in target

    (source,target) = output[3]

    assert len(source)==1
    assert "apple" in source
    assert len(target)==1
    assert "orange" in target

def test_find_parseable_ast_transaction_marker():

    sql = """

    BEGIN TRANSACTION;

    INSERT INTO dog(id) 
    SELECT id 
    FROM cat;
    
    COMMIT TRANSACTION;

    """
    asts = parse(sql=sql, dialect="tsql")

    parseable_ast = find_parseable_ast(asts=asts)

    #remove transaction marker from ast

    assert len(parseable_ast)==1
    assert isinstance(parseable_ast[0],exp.Insert)

def test_find_source_target_table_transaction():

    sql = """


    BEGIN TRANSACTION;

    INSERT INTO dog(id) 
    SELECT id 
    FROM cat;
    
    COMMIT TRANSACTION;

    """

    asts = parse(sql=sql, dialect="tsql")

    parseable_ast = find_parseable_ast(asts=asts)

    output = find_source_target_table(ast=parseable_ast[0])
    
    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==1
    assert "dog" in target



def test_find_source_target_table_try_catch_transaction():

    sql = """

    BEGIN TRY

        BEGIN TRANSACTION;

        INSERT INTO dog(id) 
        SELECT id 
        FROM cat;

        COMMIT TRANSACTION;

    END TRY
    BEGIN CATCH

        ROLLBACK TRANSACTION;

        INSERT INTO apple(id)
        SELECT id
        FROM orange;


    END CATCH
    """

    asts = parse(sql=sql, dialect="tsql")

    parseable_ast = find_parseable_ast(asts=asts)

    # 4 because of try body , try body insert , catch body , catch body insert

    assert len(parseable_ast)==4

    # try body insert

    output = find_source_target_table(ast=parseable_ast[1])

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "cat" in source
    assert len(target)==1
    assert "dog" in target

    # catch body insert
    
    output = find_source_target_table(ast=parseable_ast[3])

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "orange" in source
    assert len(target)==1
    assert "apple" in target

def test_find_parseable_ast_set():
    sql = """

    SET @foo = SELECT COUNT(*) FROM dog;

    """

    ast = parse(sql=sql,dialect="tsql")

    assert len(find_parseable_ast(ast))==1


def test_find_source_target_table_set():

    sql = """

    SET @foo = SELECT COUNT(*) FROM dog;

    """

    ast = parse_one(sql=sql,dialect="tsql")
    
    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==0

def test_find_parseable_ast_declare():
    
    sql = """

    DECLARE @foo int = SELECT COUNT(*) FROM dog;

    """

    ast = parse(sql=sql,dialect="tsql")

    assert len(find_parseable_ast(ast))==1
    
def test_find_source_target_table_declare():
    sql = """

    DECLARE @foo int = SELECT COUNT(*) FROM dog;

    """

    ast = parse_one(sql=sql,dialect="tsql")

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]

    assert len(source)==1
    assert "dog" in source
    assert len(target)==0

def test_find_parseable_ast_truncate():
    
    sql = """

    TRUNCATE TABLE foo;

    """

    ast = parse(sql=sql)

    assert len(find_parseable_ast(ast))==1

def test_find_source_target_table_truncate():
    
    sql = """

    TRUNCATE TABLE dog;

    """

    ast = parse_one(sql=sql)

    output = find_source_target_table(ast=ast)

    assert len(output)==1

    (source,target) = output[0]
    
    assert len(source)==0
    assert len(target)==1
    assert "dog" in target

def test_find_column_lineage_select():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT id,
    age
    FROM test.dog

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))
    
    assert len(lineage)==2

    source_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(source_lineage)==2
    assert source_lineage[0].source_column=="id"
    assert source_lineage[0].target_table is None
    assert source_lineage[0].target_column=="id"
    assert source_lineage[0].compute_column is None

    assert source_lineage[1].source_column=="age"
    assert source_lineage[1].target_table is None
    assert source_lineage[1].target_column=="age"
    assert source_lineage[1].compute_column is None


def test_find_column_lineage_select_alias():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT id,
    age AS test_age
    FROM test.dog

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))
    
    assert len(lineage)==2

    source_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(source_lineage)==2
    assert source_lineage[0].source_column=="id"
    assert source_lineage[0].target_table is None
    assert source_lineage[0].target_column=="id"
    assert source_lineage[0].compute_column is None

    assert source_lineage[1].source_column=="age"
    assert source_lineage[1].target_table is None
    assert source_lineage[1].target_column=="test_age"
    assert source_lineage[1].compute_column is None

def test_find_column_lineage_select_compute():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT id,
    SUM(age) AS total_age 
    FROM test.dog

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))
    
    assert len(lineage)==2

    source_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(source_lineage)==2
    assert source_lineage[0].source_column=="id"
    assert source_lineage[0].target_table is None
    assert source_lineage[0].target_column=="id"
    assert source_lineage[0].compute_column is None

    assert source_lineage[1].source_column=="age"
    assert source_lineage[1].target_table is None
    assert source_lineage[1].target_column=="total_age"
    assert source_lineage[1].compute_column is not None


def test_find_column_lineage_select_compute_different_column():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="cat",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT dog.id,
    SUM(dog.age) + SUM(cat.age) AS total_age 
    FROM test.dog
    INNER JOIN test.cat
    ON dog.id = cat.id

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table is None
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table is None
    assert dog_lineage[1].target_column=="total_age"
    assert dog_lineage[1].compute_column is not None

    cat_lineage = [x for x in lineage if x.source_table=="test.cat"]

    assert len(cat_lineage)==1
    assert cat_lineage[0].source_column=="age"
    assert cat_lineage[0].target_table is None
    assert cat_lineage[0].target_column=="total_age"
    assert cat_lineage[0].compute_column is not None

def test_find_column_lineage_select_all():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT *
    FROM test.dog

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))
    
    assert len(lineage)==2

    source_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(source_lineage)==2
    assert source_lineage[0].source_column=="id"
    assert source_lineage[0].target_table is None
    assert source_lineage[0].target_column=="id"
    assert source_lineage[0].compute_column is None

    assert source_lineage[1].source_column=="age"
    assert source_lineage[1].target_table is None
    assert source_lineage[1].target_column=="age"
    assert source_lineage[1].compute_column is None


def test_find_column_lineage_select_all_multiple_table():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="cat",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT *
    FROM test.dog
    INNER JOIN test.cat
    ON dog.id = cat.id

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table is None
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table is None
    assert dog_lineage[1].target_column=="age"
    assert dog_lineage[1].compute_column is None

    cat_lineage = [x for x in lineage if x.source_table=="test.cat"]

    assert len(cat_lineage)==2
    assert cat_lineage[0].source_column=="id"
    assert cat_lineage[0].target_table is None
    assert cat_lineage[0].target_column=="id"
    assert cat_lineage[0].compute_column is None

    assert cat_lineage[1].source_column=="age"
    assert cat_lineage[1].target_table is None
    assert cat_lineage[1].target_column=="age"
    assert cat_lineage[1].compute_column is None

def test_find_column_lineage_select_all_multiple_table_column_format():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="cat",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT dog.*,
    cat.*
    FROM test.dog
    INNER JOIN test.cat
    ON dog.id = cat.id

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table is None
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table is None
    assert dog_lineage[1].target_column=="age"
    assert dog_lineage[1].compute_column is None

    cat_lineage = [x for x in lineage if x.source_table=="test.cat"]

    assert len(cat_lineage)==2
    assert cat_lineage[0].source_column=="id"
    assert cat_lineage[0].target_table is None
    assert cat_lineage[0].target_column=="id"
    assert cat_lineage[0].compute_column is None

    assert cat_lineage[1].source_column=="age"
    assert cat_lineage[1].target_table is None
    assert cat_lineage[1].target_column=="age"
    assert cat_lineage[1].compute_column is None


def test_find_column_lineage_select_all_multiple_table_column_format_v2():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="cat",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT dog.*,
    cat.id
    FROM test.dog
    INNER JOIN test.cat
    ON dog.id = cat.id

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table is None
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table is None
    assert dog_lineage[1].target_column=="age"
    assert dog_lineage[1].compute_column is None

    cat_lineage = [x for x in lineage if x.source_table=="test.cat"]

    assert len(cat_lineage)==1
    assert cat_lineage[0].source_column=="id"
    assert cat_lineage[0].target_table is None
    assert cat_lineage[0].target_column=="id"
    assert cat_lineage[0].compute_column is None

def test_find_column_lineage_select_into():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="cat",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    
    sql = """

    SELECT *
    INTO test.insert_table
    FROM test.dog
    INNER JOIN test.cat
    ON dog.id = cat.id

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table=="test.insert_table"
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table=="test.insert_table"
    assert dog_lineage[1].target_column=="age"
    assert dog_lineage[1].compute_column is None

    cat_lineage = [x for x in lineage if x.source_table=="test.cat"]

    assert len(cat_lineage)==2
    assert cat_lineage[0].source_column=="id"
    assert cat_lineage[0].target_table=="test.insert_table"
    assert cat_lineage[0].target_column=="id"
    assert cat_lineage[0].compute_column is None

    assert cat_lineage[1].source_column=="age"
    assert cat_lineage[1].target_table=="test.insert_table"
    assert cat_lineage[1].target_column=="age"
    assert cat_lineage[1].compute_column is None


def test_find_column_lineage_select_ctas():
    

    metadata_objects:List[MetadataObject] = list()
    metadata_objects.append(
        MetadataObject(
            schema="test",\
            name="dog",\
            columns=[
                "id",\
                "age"
            ]
        )
    )

    sql = """

    CREATE TABLE foo
    WITH (
        DISTRIBUTION = ROUND_ROBIN,
        HEAP
    )
    SELECT *
    FROM test.dog

    """

    ast = parse_one(sql=sql)

    lineage = find_column_lineage(ast=ast,metadata=Metadata(host="myHost",\
                                             database="myDb",
                                             objects=metadata_objects))

    dog_lineage = [x for x in lineage if x.source_table=="test.dog"]

    assert len(dog_lineage)==2
    assert dog_lineage[0].source_column=="id"
    assert dog_lineage[0].target_table=="foo"
    assert dog_lineage[0].target_column=="id"
    assert dog_lineage[0].compute_column is None

    assert dog_lineage[1].source_column=="age"
    assert dog_lineage[1].target_table=="foo"
    assert dog_lineage[1].target_column=="age"
    assert dog_lineage[1].compute_column is None


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
    test_has_table_merge()

    test_find_parseable_ast()

    test_find_source_target_table_single_insert_into_with_database_schema()

    test_physical_column()
    test_find_source_target_table_if()
    test_find_source_target_table_if_else()
    test_find_source_target_table_if_elseif()
    test_find_source_target_table_if_elseif_else()
    test_find_source_target_table_nested_if()
    test_find_source_target_table_while()
    test_find_source_target_table_merge()
    test_find_source_target_table_merge_alias()
    test_find_source_target_table_merge_cte()

    test_find_source_target_table_try()
    test_find_source_target_table_try_catch()
    test_find_source_target_table_try_catch_multi_statement()

    test_find_parseable_ast_transaction_marker()

    test_find_source_target_table_try_catch_transaction()
    test_find_source_target_table_transaction()

    test_find_parseable_ast_set()
    test_find_source_target_table_set()

    test_find_parseable_ast_declare()
    test_find_source_target_table_declare()

    test_find_parseable_ast_truncate()
    test_find_source_target_table_truncate()

    test_find_column_lineage_select()
    test_find_column_lineage_select_alias()
    test_find_column_lineage_select_compute()
    test_find_column_lineage_select_compute_different_column()
    test_find_column_lineage_select_all()
    test_find_column_lineage_select_all_multiple_table()
    test_find_column_lineage_select_all_multiple_table_column_format()
    test_find_column_lineage_select_all_multiple_table_column_format_v2()
    test_find_column_lineage_select_into()
    test_find_column_lineage_select_ctas()

if __name__=="__main__":
    tests()
