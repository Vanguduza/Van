FROM supabase/gotrue:v2.196.0 AS gotrue
FROM postgrest/postgrest:v14.17 AS postgrest
FROM supabase/postgres:17.6.1.136
USER root
RUN apk add --no-cache python3 nginx
COPY --from=gotrue /usr/local/bin/auth /fixture-bin/auth
COPY --from=gotrue /usr/local/etc/auth/migrations /fixture-bin/migrations
COPY --from=postgrest /usr/bin/postgrest /fixture-bin/postgrest
COPY source /fixture-source
RUN chmod -R a+rX /fixture-source /fixture-bin
USER 100:101
ENTRYPOINT ["/usr/bin/python3", "/fixture-source/tests/rehearse_native.py"]
