sudo cp /home/ec2-user/elasticsearch.yml /usr/local/elasticsearch/config/elasticsearch.yml
sudo chmod 600 /usr/local/elasticsearch/config/elasticsearch.yml
sudo cp /home/ec2-user/elasticsearch.in.sh /usr/local/elasticsearch/bin/elasticsearch.in.sh

cd /usr/local/elasticsearch

# RUN IN BACKGROUND
sudo bin/elasticsearch -p current_pid.txt &
disown -h
cd /data/logs
tail -f ekyle-aws-1.log