CREATE TABLE iris (
    sepal_length FLOAT,
    sepal_width FLOAT,
    petal_length FLOAT,
    petal_width FLOAT,
    species STRING) USING R2 OPTIONS (
    table '101',
    host 'localhost',
    port '18101',
    partitions 'sepal_length sepal_width',
    mode 'nvkvs',
    group_size '5',
    query_result_partition_cnt_limit '40000',
    query_result_task_row_cnt_limit '10000',
    query_result_total_row_cnt_limit '100000000',
    transformations '[
    {
    "index": "sepal_length",
    "value": "$(sepal_length).length()<12? \"000000000000\" :$(sepal_length).substring(0, 11).concat( \"0\" )"
    },
    {
    "index": "petal_length",
    "value": "$(petal_length).length() != 0 && $(petal_length).substring(0, 2).equals(\"T1\")?\"T1\": \"O\""
    },
    {
    "index": "species",
    "value": "fnvHash(petal_width, 10)"
    }
    ]'
)