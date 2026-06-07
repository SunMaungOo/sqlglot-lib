from sqlglot import parse_one,exp,optimizer,parse
from sqlglot.optimizer import traverse_scope,Scope
from sqlglot.optimizer.scope import build_scope
from typing import Set,Dict,List,Tuple,Optional
from sqlglot.expressions import Expression
import re
from dataclasses import dataclass
from sqlglot.schema import MappingSchema
from collections import defaultdict

@dataclass(frozen=True)
class Metadata:
    host:str
    database:str
    objects:List[MetadataObject]

@dataclass(frozen=True)
class MetadataObject:
    schema:str
    name:str
    columns:List[str]

@dataclass(frozen=True)
class ColumnLineage:
    #schema.table format
    source_table:str
    source_column:str
    target_table:Optional[str]
    target_column:str 
    # raw sql expression if it is compute column
    compute_column:Optional[str] 


def find_base_tables(ast:Expression)->Set[str]:
    
    ctes:Set[str] = set()

    tables:Set[str] = set()

    for cte in ast.find_all(exp.CTE):
        ctes.add(cte.alias_or_name)

    for table in ast.find_all(exp.Table):
        #ignore if the table is the cte
        if table.name not in ctes:
            tables.add(internal_get_table_name(table))

    return tables

def find_cte_dependencies(ast:Expression)->Dict[str,List[str]]:
    """
    key = cte name
    values = list of table name and cte used in the key "cte"
    """
    dependencies = dict()

    for cte in ast.find_all(exp.CTE):

        dependencies[cte.alias_or_name] = []

        #get the sql statement used in the cte

        query = cte.this.sql()

        for table in parse_one(query).find_all(exp.Table):
            dependencies[cte.alias_or_name].append(internal_get_table_name(table))

    return dependencies

def find_table_relationship(ast:Expression)->List[Tuple[str,str]]:
    """
    Find how the table are linked , joined together

    first item = FROM table
    second item = table that from table is joined to
    """

    relationships:List[Tuple[str,str]] = list()

    for join_stm in ast.find_all(exp.Join):
        joined_table = find_base_tables(join_stm).pop()

        for from_stm in join_stm.parent_select.find_all(exp.From):

            from_table = internal_get_table_name(from_stm)

            #from_table = from_stm.name

            relationships.append((from_table,joined_table))

    return relationships

def qualify_columns(expression:Expression, schema:str):
    try:      
        expression = optimizer.qualify_tables.qualify_tables(expression)
        expression = optimizer.isolate_table_selects.isolate_table_selects(expression)
        expression = optimizer.qualify_columns.qualify_columns(expression, schema)

    except Exception as e:
        pass  
 
    return expression

def find_physical_column(ast:Expression)->List[Tuple[str,str]]:
    """
    Return List of tuple

    The first item of tuple is the table name and the second item of tuple is column name
    """

    """
    SELECT id
    FROM foo

    Change the above id column to foo.id 
    """
    ast = qualify_columns(ast,schema=None)

    physical_columns:List[Tuple[str,str]] = list()

    for scope in traverse_scope(ast):
         for column in scope.columns:
            if isinstance(scope.sources.get(column.table),exp.Table):
                physical_columns.append((scope.sources.get(column.table).name , column.name))

    return physical_columns


def find_column_lineage(ast:Expression,metadata:Metadata,dialect="tsql")->List[ColumnLineage]:

    schema_mapping = internal_get_schema_mapping(metadata=metadata)

    lineage:List[ColumnLineage] = list()

    try:

        ast = optimizer.qualify_tables.qualify_tables(ast, dialect=dialect)
        ast = optimizer.qualify_columns.qualify_columns(ast, schema_mapping, dialect=dialect)
        
    except Exception:
        pass
    
    if internal_is_merge(ast):
        lineage = internal_find_merge_column_lineage(ast=ast) 
    elif internal_is_insert_into(ast):
        lineage = internal_find_insert_into_column_lineage(ast=ast)
    elif ast.find(exp.Update):
        lineage = internal_find_update_column_lineage(ast=ast)
    elif internal_is_contain_select(ast=ast):
        lineage = internal_find_select_column_lineage(ast=ast)


    return lineage

def find_ambiguous_column_lineage(column_lineage:List[ColumnLineage])->Dict[str,List[ColumnLineage]]:
    """
    Ambiguous column = column lineage which goes to same target column from different source table

    key = target column

    """

    # Same column from different source system goes to same non-compute target column of the target 

    non_compute_columns = [lineage for lineage in column_lineage\
                           if lineage.compute_column is None]
    
    grouped:Dict[str,List[ColumnLineage]] = defaultdict(list)

    for lineage in non_compute_columns:
        grouped[lineage.target_table].append(lineage)

    return {
        key: value\
        for key, value in grouped.items()\
        if len(value) > 1
    }

def internal_find_update_column_lineage(ast:Expression)->List[ColumnLineage]:
    
    # ast = update node

    lineage:List[ColumnLineage] = list()

    target_table = internal_find_update_node_table_name(ast=ast)

    if target_table is None:
        return list()
    
    #exclude update target table name from map
    # key = alias name , value = full table name

    alias_map:Dict[str,str] = {
        table.alias_or_name:internal_get_table_name(table)
        for table in ast.find_all(exp.Table)
        if table.alias_or_name!=target_table
    }

    for node in ast.expressions:

        if not isinstance(node,exp.EQ):
            continue
        
        equal_node = node
        
        update_left_side = equal_node.left

        update_right_side = equal_node.right

        if not isinstance(update_left_side,exp.Column):
            continue

        target_column = update_left_side.name

        for column in update_right_side.find_all(exp.Column):

            source_table = alias_map[column.table]

            source_column = column.name

            transformation = None

            if not isinstance(update_right_side,exp.Column):
                transformation = update_right_side.sql()

            lineage.append(
                ColumnLineage(
                    source_table=source_table,
                    source_column=source_column,
                    target_table=target_table,
                    target_column=target_column,
                    compute_column=transformation
                )
            )
             
    return lineage

def internal_find_merge_column_lineage(ast:Expression)->List[ColumnLineage]:

    # ast = Merge

    lineage:List[ColumnLineage] = list()

    if not ast.find(exp.Merge):
        return list()

    merge_node = ast

    target_table = internal_get_table_name(merge_node.this)

    alias_map:Dict[str,str] = {
        table.alias_or_name:internal_get_table_name(table)
        for table in ast.find_all(exp.Table)
        if table.alias_or_name!=target_table
    }

    for when_node in merge_node.find_all(exp.When):

        then_node = when_node.args.get("then")

        if then_node is None:
            continue

        if not (isinstance(then_node,exp.Update) or\
        isinstance(then_node,exp.Insert)):
            continue
        
        # WHEN MATCHED THEN UPDATE SET ... = ...

        if isinstance(then_node,exp.Update):

            for equal_node in then_node.find_all(exp.EQ):

                update_left_side = equal_node.left

                update_right_side = equal_node.right

                if not isinstance(update_left_side,exp.Column):
                    continue

                target_column = update_left_side.name

                transformation = None

                if not internal_is_direct_column_mapping(update_right_side):
                    transformation = update_right_side.sql()

                for column in update_right_side.find_all(exp.Column):

                    source_table = alias_map[column.table]

                    source_column = column.name

                    lineage.append(
                        ColumnLineage(
                            source_table=source_table,
                            source_column=source_column,
                            target_table=target_table,
                            target_column=target_column,
                            compute_column=transformation
                        )
                    )

        # WHEN NOT MATCHED THEN INSERT (...) VALUES (...)

        elif isinstance(then_node,exp.Insert):

            target_columns = [column.name for column in then_node.this.expressions]

            source_column_expressions = then_node.expression

            for target_column,source_column_expression in zip(target_columns,source_column_expressions):

                transformation = None

                if not internal_is_direct_column_mapping(source_column_expression):
                    transformation = source_column_expression.sql()

                for column in source_column_expression.find_all(exp.Column):

                    source_table = alias_map[column.table]

                    source_column = column.name

                    lineage.append(
                        ColumnLineage(
                            source_table=source_table,
                            source_column=source_column,
                            target_table=target_table,
                            target_column=target_column,
                            compute_column=transformation
                        )
                    )

            
    return lineage



def internal_find_insert_into_column_lineage(ast:Expression)->List[ColumnLineage]:
    
    lineage:List[ColumnLineage] = list()

    # ast = insert node

    insert_table_name = internal_find_insert_into_node_table_name(ast=ast)

    if insert_table_name is None:
        return list()
    
    target_columns:List[str] = list()

    if isinstance(ast.this,exp.Schema):

        schema_node = ast.this

        # get the column name from INSERT INTO foo(c1,c2)

        target_columns = [column.name for column in schema_node.find_all(exp.Identifier)]

    if len(target_columns)==0:
        return list()

    select_statement = ast.find(exp.Select)

    if select_statement is None:
        return list()

    for index,expression in enumerate(select_statement):

        target_column = internal_get_output_alias_or_column(expression)

        if index<len(target_columns):
            target_column = target_columns[index]

        for scope in traverse_scope(select_statement):

            for source_table,source_column in internal_get_source_column(node=expression,scope=scope):

                transformation = None

                if not internal_is_direct_column_mapping(expression):
                    transformation = expression.sql()

                lineage.append(
                    ColumnLineage(
                        source_table=source_table,
                        source_column=source_column,
                        target_table=insert_table_name,
                        target_column=target_column,
                        compute_column=transformation
                    )
                )
    
    return lineage


def internal_find_select_column_lineage(ast:Expression)->List[ColumnLineage]:
    """
    Handle simple select , select into , create table as select (CTAS)
    """

    lineage:List[ColumnLineage] = list()

    target_statement = find_source_target_table(ast=ast)

    target_table = None
    
    if len(target_statement)>0:

        targets = target_statement[0][1]

        if len(targets)>0:
            target_table = targets[0]
 
    for scope in traverse_scope(expression=ast):
        
        select = scope.expression

        if not isinstance(select, exp.Select):
            continue

        for alias_or_column in select.expressions:
            
            target_column = internal_get_output_alias_or_column(node=alias_or_column)

            for source_table,source_column in internal_get_source_column(node=alias_or_column,scope=scope):
                
                transformation = None

                if not internal_is_direct_column_mapping(alias_or_column):
                    transformation = alias_or_column.sql()

                lineage.append(
                    ColumnLineage(
                        source_table=source_table,
                        source_column=source_column,
                        target_table=target_table,
                        target_column=target_column,
                        compute_column=transformation
                    )
                )

    return lineage

def internal_is_direct_column_mapping(node:Expression)->bool:

    inner = node 

    if isinstance(node,exp.Alias):
        inner = node.this

    return isinstance(inner,exp.Column)

def internal_get_schema_mapping(metadata:Metadata)->MappingSchema:

    schema_mapping:dict = {
        metadata.database:{}
    }
    
    database_mapping = schema_mapping[metadata.database]

    for obj in metadata.objects:

        if obj.schema not in database_mapping:
            database_mapping[obj.schema] = {}
        
        database_mapping[obj.schema][obj.name] = {
            column:"UNKNOWN"
            for column in obj.columns
        }

    return MappingSchema(schema_mapping)
            

def internal_get_output_alias_or_column(node:Expression)->str:
    """
    Get column name or alias name of the node
    """
    if isinstance(node,exp.Alias):
        return node.alias
    elif isinstance(node,exp.Column):
        return node.name
    
    # for unidentified expression like SUM(...) , COUNT(...),...

    return node.sql()

def internal_get_source_column(node:Expression,scope:Scope)->List[Tuple[str,str]]:
    """
    Get the List[(table excluding CTE,column)].
    """

    result:List[Tuple[str,str]] = list()

    search_node:Expression = node

    if isinstance(node,exp.Alias):
        search_node = node.this
    
    for column in search_node.find_all(exp.Column):
        
        # get the table back from column (this work because the the table name are qualify) (column is in table.column format)

        table_alias = column.table

        source = scope.sources.get(table_alias)

        if isinstance(source,exp.Table):
            result.append((internal_get_table_name(source),column.name))


    return result

def find_source_target_table(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name excluding cte , List of target table name)]
    """

    #we use set because the source table can be multiple scope (such as case with CTE)

    source:Set[str] = set()

    target:List[str] = list()

    output:List[Tuple[Set[str],List[str]]] = list()
    
    if internal_is_set(ast):
        return internal_find_set_source_target(ast)
    if internal_is_declare(ast):
        return internal_find_declare_source_target(ast)
    elif internal_is_branch(ast):
        return internal_find_branch_source_target(ast)
    elif internal_is_merge(ast):
        (source,target) = internal_find_merge_source_target(ast)
    elif internal_is_try(ast):
        return internal_find_try_source_target(ast)
    elif internal_is_catch(ast):
        return internal_find_catch_source_target(ast)
    elif internal_is_contain_select(ast) and not internal_is_dml_or_ddl(ast):
        (source,target) = internal_find_select_statement_source_target(ast)
    elif internal_is_rename_table(ast):
        (source,target) = internal_find_rename_table_source_target(ast)
    elif internal_is_transaction(ast):
        return output
    elif isinstance(ast,exp.Block):
        for expression in ast.expressions:
            output.extend(find_source_target_table(ast=expression))
            
    else:

        if internal_is_insert_into(ast):


            # INSERT INTO statement source table must be find with SELECT statement source table (parse FROM and JOIN)
            (source,_) = internal_find_select_statement_source_target(ast)

            table_name = internal_find_insert_into_node_table_name(ast)

            target = [table_name]

        elif internal_is_truncate(ast):

            target = [find_base_tables(ast).pop()] 
            
        else:
            
            table_name = internal_find_update_node_table_name(ast)

            #if it not an UPDATE statement , try to find it is a DELETE statement

            if table_name is None:
                table_name = internal_find_delete_node_table_name(ast)

            if table_name is None:
                table_name = internal_find_create_table_node_table_name(ast)

            if table_name is not None:
                target = [table_name]
            
            source = find_base_tables(ast)

            #for the CREATE TABLE statement , the parser mistake the CREATE TABLE statement as source so 
            #we got to remove it 
            if internal_is_contain_create_table(ast):
                source.remove(target[0])
            
        
    #if we do not find any target , it could be DDL or DML statement. The above work because we can still get the source table
    #because FROM , JOIN only can be parse with select statement

    if len(source)>0 or len(target)>0:
        output.append((source,target))

    return output


def has_table(ast:Expression)->bool:
    """
    Check whether the AST contain table we can parse
    """

    return internal_is_contain_select(ast) or\
          internal_is_dml_or_ddl(ast) or\
          internal_is_rename_table(ast) or\
          internal_is_merge(ast)

def internal_is_try(ast:Expression)->bool:
    """
    Check whether it start with BEGIN TRY
    """
    command_expression = ast

    if isinstance(ast,exp.Block):
        command_expression = ast.expressions[1]
    
    if not isinstance(command_expression,exp.Command):
        return False
    
    if command_expression.name!="BEGIN":
        return False
        
    expression_text = str(command_expression.expression).strip()

    return expression_text.upper().startswith("TRY")

def internal_is_catch(ast:Expression)->bool:
    """
    Check whether it is BEGIN CATCH
    """
    command_expression = ast

    if isinstance(ast,exp.Block):
        command_expression = ast.expressions[0]
    
    if not isinstance(command_expression,exp.Command):
        return False
    
    expression_text = str(command_expression.expression).strip()
    
    return bool(re.search(r'BEGIN\s+CATCH', expression_text, re.IGNORECASE))

def internal_is_declare(ast:Expression)->bool:
    """
    Check whether it is the declare statement which also set the value
    """
    command = ast.find(exp.Command)

    if command is None:
        return False
    
    if command.name.upper()!="DECLARE":
        return False
    
    expression = command.expression

    if expression is None:
        return False
    
    literal = str(expression)

    return len(split_empty_array(text=literal,sep="="))>=2


def internal_is_rename_table(ast:Expression)->bool:
    """
    Check if it contain the rename table statement
    """

    command = ast.find(exp.Command)

    if command is None:
        return False
    
    if command.name!="RENAME":
        return False
    
    expressions = command.expression

    if expressions is None:
        return False
    
    literal = expressions[0].name.lower()

    blocks = split_empty_array(text=literal,sep=" ")

    is_found_object_literal = False

    is_found_to_literal = False

    # find whether it is in RENAME OBJECT .... TO .... format

    for word in blocks:
        if word == "object":
            is_found_object_literal = True
        elif word == "to":
            is_found_to_literal = True
        
    return len(blocks)==4 and\
        is_found_object_literal\
        and is_found_to_literal

def internal_is_branch(ast:Expression)->bool:
    """
    Check if it contain the branching statement
    """
    return ast.find(exp.IfBlock) is not None or\
    ast.find(exp.WhileBlock) is not None

def internal_is_merge(ast:Expression)->bool:
    return ast.find(exp.Merge) is not None

def internal_is_set(ast:Expression)->bool:
    return ast.find(exp.Set) is not None

def split_empty_array(text:str,sep:str)->List[str]:
    """
    Split while removing the empty block
    """

    blocks = text.split(sep=sep)

    new_blocks = []

    for block in blocks:
        if block.strip()=="":
            continue

        new_blocks.append(block)


    return new_blocks

def internal_find_merge_source_target(ast:Expression)->Tuple[Set[str],List[str]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    merge = ast.find(exp.Merge)

    source:Set[str] = set()

    target:List[str] = list()

    if merge is None:
        return (source,target)
    
    target_table_node = merge.this

    if isinstance(target_table_node,exp.Table):
        target.append(internal_get_table_name(target_table_node))
    
    ctes:Dict[str,List[str]] = find_cte_dependencies(ast)

    using_node = merge.args.get("using")

    if using_node is not None:

        for table_expression in using_node.find_all(exp.Table):

            table_name = table_expression.name

            # expand the base table of cte

            if table_name in ctes:
                source = source.union(ctes[table_name])
            else:
                source.add(internal_get_table_name(table_expression))



    # make sure target table is not listed as its own source

    for table in target:
        source.discard(table)
    

    return (source,target)

def internal_find_set_source_target(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    output:List[Tuple[Set[str],List[str]]] = list()

    set_item_expression = ast.find(exp.SetItem)

    if set_item_expression is None:
        return list()
    
    for select_expression in set_item_expression.find_all(exp.Select):
        output.extend(find_source_target_table(select_expression))

    return output


def internal_find_branch_source_target(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    output:List[Tuple[Set[str],List[str]]] = list()

    if_block = ast.find(exp.IfBlock)

    while_block = ast.find(exp.WhileBlock)

    if if_block is None and\
        while_block is None:
        return list()
    
    if if_block is not None:

        if "true" in if_block.args\
            and if_block.args["true"]:

            for expression in if_block.args["true"].expressions:
                output.extend(find_source_target_table(ast=expression))

        if "false" in if_block.args\
            and if_block.args["false"]:

            for expression in if_block.args["false"].expressions:
                output.extend(find_source_target_table(ast=expression))

    elif while_block is not None:
        for expression in while_block.args["body"].expressions:
            output.extend(find_source_target_table(ast=expression))
    
    return output

def internal_find_declare_source_target(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    output:List[Tuple[Set[str],List[str]]] = list()

    if not internal_is_declare(ast):
        return list()
    
    command = ast.find(exp.Command)

    expression = command.expression

    literal = str(expression)

    blocks = split_empty_array(text=literal,sep="=")

    declare_body = "".join(blocks[1:])

    inner_asts = parse(declare_body,dialect="tsql")
            
    for inner_ast in find_parseable_ast(asts=inner_asts):
        output.extend(find_source_target_table(inner_ast))
    
    return output

def internal_find_try_source_target(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    output:List[Tuple[Set[str],List[str]]] = list()
    
    if not isinstance(ast,exp.Command):
        return list()

    expression_text = str(ast.expression)

    # remove TRY prefix and whitespace and new line

    try_body = re.sub(r'^\s*TRY\s*\n?',\
                      '',\
                    expression_text,\
                    flags=re.IGNORECASE).strip()

    if try_body:
        try:
            inner_asts = parse(try_body,dialect="tsql")
            
            for inner_ast in find_parseable_ast(asts=inner_asts):
                output.extend(find_source_target_table(inner_ast))
        except Exception:
            pass

    
    return output

def internal_find_catch_source_target(ast:Expression)->List[Tuple[Set[str],List[str]]]:
    """
    List[(Set of source table name, List of target table name)]
    """
    output:List[Tuple[Set[str],List[str]]] = list()

    if not isinstance(ast,exp.Command):
        return list()

    expression_text = str(ast.expression)

    parts = re.split(r'BEGIN\s+CATCH\s*\n?',\
                     expression_text,\
                    flags=re.IGNORECASE)

    if len(parts)<2:
        return output

    catch_body = parts[-1].strip()

    # there is weird single quote at end 

    catch_body = catch_body.removesuffix("'")

    if catch_body:

        try:
            inner_asts = parse(catch_body,dialect="tsql")
            
            for inner_ast in find_parseable_ast(asts=inner_asts):
                output.extend(find_source_target_table(inner_ast))
        except Exception:
            pass

    return output

def internal_find_rename_table_source_target(ast:Expression)->Tuple[Set[str],List[str]]:
    """
    (Set of source table name, List of target table name)
    """

    source:Set[str] = set()

    target:List[str] = list()

    command = ast.find(exp.Command)

    if command.name == "RENAME":

        expression = command.expression

        literal = expression[0].name

        blocks = split_empty_array(text=literal.strip(),sep=" ")

        removed_blocks = []

        for block in blocks:
        
            lower = block.lower()

            if lower=="object" or lower=="to":
                continue

            removed_blocks.append(block)

        
        source_table = removed_blocks[0]

        target_block = removed_blocks[1]

        source_dot_blocks = source_table.split(".")

        source_prefix = ""


        for index in range(len(source_dot_blocks)-1):
            source_prefix+=f"{source_dot_blocks[index]}."

        target_table = source_prefix+target_block

        source.add(source_table)
        target.append(target_table)

    return (source,target)

def internal_find_select_statement_source_target(ast:Expression)->Tuple[Set[str],List[str]]:
    """
    (Set of source table name excluding cte , List of target table name)
    """

    source:Set[str] = set()

    target:List[str] = list()

    for cte_ast in ast.find_all(exp.CTE):

        for base_table in find_base_tables(ast=cte_ast):

            source.add(base_table)

    root = build_scope(ast)

    if root is None:
        return (source,target)

    for scope in root.traverse():
        
        cte_names = [cte.alias for cte in scope.ctes]

        all_physical_tables = [internal_get_table_name(table) for table in scope.tables if table.name not in cte_names]
        
        #table which is found in FROM or JOIN statement

        from_join_tables = [

            internal_get_table_name(source) for alias,(node,source) in scope.selected_sources.items() if isinstance(source,exp.Table)

        ]

        source.update(from_join_tables)

        #try to get the target only if the target have not been found in previous scope

        if len(target)==0:
            target = [table for table in all_physical_tables if table not in source and table]

    return (source,target) 

def internal_is_contain_select(ast:Expression)->bool:
    """
    Check if it contain the select statement
    """
    return ast.find(exp.Select) is not None

def internal_is_contain_create_table(ast:Expression)->bool:
    """
    Check whether it contains the create table statement
    """
    return ast.find(exp.Create) is not None 

def internal_find_insert_into_node_table_name(ast:Expression)->Optional[str]:
    """
    Find the target table name we INSERT INTO
    """
    node = ast.find(exp.Insert)

    #if it is a INSERT INTO statement

    if node is None:
        return None 
    
    table = node.this.find(exp.Table)

    #put the INSERT INTO table name as the target
    return internal_get_table_name(table)

def internal_find_update_node_table_name(ast:Expression)->Optional[str]:
    """
    Find the table that we UPDATE to
    """
    node = ast.find(exp.Update)

    #if it is a Update statement

    if node is None:
        return None 
    
    table = node.this.find(exp.Table)

    #put the UPDATE table name as the target
    return internal_get_table_name(table)

def internal_find_delete_node_table_name(ast:Expression)->Optional[str]:
    """
    Find the table that we DELETE from
    """
    node = ast.find(exp.Delete)

    #if it is a DELETE statement

    if node is None:
        return None 
    
    table = node.this.find(exp.Table)

    #put the DELETE table name as the target
    return internal_get_table_name(table)

def internal_find_create_table_node_table_name(ast:Expression)->Optional[str]:
    """
    Find the table that we CREATE TABLE from
    """
    node = ast.find(exp.Create)

    #if it is a  CREATE TABLE statement

    if node is None:
        return None 


    table = node.find(exp.Table)

    #put the CREATE TABLE table name as the target
    return internal_get_table_name(table)

def internal_is_dml_or_ddl(ast:Expression)->bool:
    return ast.find(exp.Insert) is not None\
    or ast.find(exp.Update) is not None\
    or ast.find(exp.Delete) is not None\
    or ast.find(exp.Create) is not None\
    or ast.find(exp.Drop) is not None


def internal_is_insert_into(ast:Expression)->bool:
    return ast.find(exp.Insert) is not None

def internal_is_transaction(ast:Expression)->bool:
    return isinstance(ast,(exp.Transaction,exp.Commit,exp.Rollback))

def internal_is_truncate(ast:Expression)->bool:
    return ast.find(exp.TruncateTable) is not None

def find_parseable_ast(asts:List[Expression])->List[Expression]:
    """
    Get the ast we can parse. 
    Ignore statement with non table related statement
    Return list[AST]
    """

    parseable_ast:List[Expression] = list()

    for ast in asts:

        if ast is None:
            continue
        
        # we still need to get try body

        if internal_is_try(ast):
            parseable_ast.append(ast)
            continue
        
        # we need to get catch body
        
        if internal_is_catch(ast):
            parseable_ast.append(ast)
            continue

        if internal_is_set(ast):
            parseable_ast.append(ast)
            continue

        if internal_is_declare(ast):
            parseable_ast.append(ast)
            continue
        
        if internal_is_truncate(ast):
            parseable_ast.append(ast)
            continue

        # skip if it the transaction marker

        if internal_is_transaction(ast):
            continue

        if has_table(ast):
            parseable_ast.append(ast)
            continue

        if isinstance(ast,exp.Command):
            continue

    return parseable_ast


def internal_get_table_name(table_expression:Expression)->str:
    """
    From the table_expression , try to get the table name in 
    database.schema.table format
    """

    database_name = None

    schema_name = None

    table_name = table_expression.name

    if "db" in table_expression.args.keys() and table_expression.args["db"] is not None:
        schema_name = table_expression.args["db"].name

    if "catalog" in table_expression.args.keys() and table_expression.args["catalog"] is not None:
        database_name = table_expression.args["catalog"].name

    return internal_add_surfix(database_name,".","") + internal_add_surfix(schema_name,".","") + table_name

def internal_add_surfix(text:str,surfix:str,false_value:str)->str:
    if text is None:
        return false_value
    
    return text+surfix
