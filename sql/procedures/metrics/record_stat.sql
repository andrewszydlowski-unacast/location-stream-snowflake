-- Ported from flowdefs/LocationStream/03_record_locationstream_stat.sql
CREATE OR REPLACE PROCEDURE {{ database }}.{{ schema_prefix }}METRICS.RECORD_STAT(
    JOB_ID VARCHAR,
    JOB_TYPE VARCHAR,
    STATNAME VARCHAR,
    STATDESC VARCHAR,
    AGGTYPE VARCHAR,
    STATVALUE FLOAT,
    EXTRADETAILS VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
-- Version 4.0 - Dynamic SQL with USING clause for clean parameter binding
DECLARE
    sql_stmt STRING;
BEGIN

    sql_stmt := 'INSERT INTO {{ database }}.{{ schema_prefix }}METRICS.STATS ';
    sql_stmt := sql_stmt || '(JOBID, JOBTYPE, STATNAME, STATDESC, AGGTYPE, STATVALUE, EXTRADETAILS) ';
    sql_stmt := sql_stmt || 'SELECT ?, UPPER(?), UPPER(?), ?, UPPER(?), ?, PARSE_JSON(?)';

    EXECUTE IMMEDIATE sql_stmt USING (JOB_ID, JOB_TYPE, STATNAME, STATDESC, AGGTYPE, STATVALUE, EXTRADETAILS);

    RETURN 'Stat recorded successfully: ' || :STATNAME;
END;
$$;
