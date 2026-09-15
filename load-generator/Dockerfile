FROM eclipse-temurin:17-jre-jammy

ARG JMETER_VERSION=5.6.3

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && curl -fsSL "https://dlcdn.apache.org/jmeter/binaries/apache-jmeter-${JMETER_VERSION}.tgz" -o /tmp/jmeter.tgz \
    && mkdir -p /opt/jmeter \
    && tar -xzf /tmp/jmeter.tgz -C /opt/jmeter --strip-components=1 \
    && rm /tmp/jmeter.tgz \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/jmeter/bin:${PATH}"

WORKDIR /load-generator
COPY . .

ENTRYPOINT ["jmeter", "-n"]
CMD ["-t", "load_test.jmx"]
