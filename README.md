hpfeeds
=======

Check out our hpfeeds setup with a social sharing model: http://hpfriends.honeycloud.net/

There is a nice introduction by heipei to be read here: http://heipei.github.io/2013/05/11/Using-hpfriends-the-social-data-sharing-platform/

This is the reference implementation repository. By now hpfeeds exists in other languages than Python and C as well! Check out the following implementations:
 - Go: https://github.com/fw42/go-hpfeeds
 - Ruby: https://github.com/fw42/hpfeedsrb
 - More Ruby: https://github.com/vicvega/hpfeeds-ruby
 - JS (within node.js): https://github.com/fw42/honeymap/blob/master/server/node_modules/hpfeeds/index.js

## About
hpfeeds is a lightweight authenticated publish-subscribe protocol that supports arbitrary binary payloads.

We tried to design a simple wire-format so that everyone is able to subscribe to the feeds with his favorite language in almost no time.

Different feeds are separated by channels and support arbitrary binary payloads. This means that the channel users have to decide about the structure of data. This could for example be done by choosing a serialization format.

Access to channels is given to so-called Authkeys which essentially are pairs of an identifier and a secret. The secret is sent to the server by hashing it together with a per-connection nonce. This way no eavesdroppers can obtain valid credentials. Optionally the protocol can be run on top of SSL/TLS, of course.

To support multiple data sources and sinks per user we manage the Authkeys in this webinterface after a quick login with a user account. User accounts are only needed for the webinterface - to use the data feed channels, only Authkeys are necessary. Different Authkeys can be granted distinct access rights for channels.

## Wire Protocol

Each message carries a message header. The message types can make use of "parameters" that are being sent as (length,data) pairs.

```
struct MsgHeader {
    uint32_t messageLength; // total message size, including this
    uint8_t opCode;        // request type - see table below
};
```

For example the publish message would consist of message header, length(client_id), client id, length(channelname), channelname, payload. The payload, can be arbitrary binary data.
On the wire this would look like:

```
length | opcode | next | identifier | next | channelname | payload
----------------------------------------------------------------------------------------------------------------------------
    85        3   9      b4aa2@hp1    9      mwcapture     137941a3d8589f6728924c08561070bceb5d72b8,http://1.2.3.4/calc.exe
```

### Message types

* error (0): errormessage
* info (1): server name, nonce
* auth (2): client id, sha1(nonce+authkey)
* publish (3): client id, channelname, payload
* subscribe (4): client id, channelname
* For further details and definition of each message type, consider the page about the example CLI which describes how to speak the wire protocol.

### Authentication

* Server sends a nonce per connection
* Client sends id and sha1(nonce+authkey) hash
* Server looks up authkey by id and checks hash
* Server looks up subscribe/publish ACL for this client

### Usage

## Hpfeeds in Actions

Hpfeeds 的訊息傳遞主要透過 broker 進行，因此我們在進行資料(payload)的發佈與訂閱時，都要透過 broker 進行。
所以首先必須確定有 broker 為我們處理資料傳遞的工作。

而使用者與使用者之間發佈與訂閱的過程，都需要透過管道(channel)，因此 broker 也必須記錄 channel 資訊，才知道哪些資料要發佈至哪些使用者，或者哪些使用者可以訂閱哪些頻道。

若以圖來表示會像下圖：

         subscribe channel 1             publish to channel1
user A <----------------------  broker <-----------------------  user B
                                |
                                |
                    database of broker
                    user A can subscribe channel1
                    user B can publish to channe1


Hpfeeds 所提供的 broker 在 `broker/` 資料夾底下。其資料夾結構如下：

```
broker
├── broker.py
├── config.py
├── database.py
├── proto.py
├── testbroker.py
└── utils.py
└── requirements.txt
```

`broker.py` 是我們的主程式
`config.py` broker 的設定檔
`database.py` broker 所需要的資料庫，包括可以連上 broker 的使用者資訊以及channel資料等等。
`proto.py` Wire Protocol的實作
`testbroker.py` 測試用的broker
`utils.py` 定義例外類別與相關function
`requirements.txt` 相關套件相依性

安裝 broker

```
pip install -r requirements.txt
```

啟動 broker

```
python broker.py
```

### 新增使用者

因為使用 broker 時需要進行認證，因此就需要在資料庫中新增相關的使用者帳號資訊。
啟動 broker 之後會產生一個 db.sqlite3 ，我們可以用以下指令新增一位使用者進行測試。

```
$ sqlite3 db.sqlite3
sqlite> insert into authkeys (owner, ident, secret, pubchans, subchans) values ('owner', 'ident', 'secret', '["chan1"]', '["chan1"]');
```

上述SQL語法將是將使用者資訊加入到 `authkeys` 這個表格：
擁有者名稱               owner  /* 單純為了識別db裡的記錄是誰新增的 */
連線時識別碼             ident  /* 發佈或訂閱時需使用此識別碼 */
訂閱或發佈時所需要的密語 secret /* 發佈或訂閱時需使用此密語 */
可發佈的頻道名稱         chan1  /* 多個頻道 ['chan1', 'chan2', ...] */
可訂閱的頻道名稱         chan1  /* .... */


### 利用 hpfeeds-client.py 進行發佈與訂閱的測試

有了 broker 就可以用 hpfeeds-client 進行測試


1. 安裝 hpfeeds

python setup.py install

2. 啟動一個 subscribe

./hpfeeds-client -i ident -s secret --host <your_broker_host> -p <your_broker_port> -c chan1 subscribe

3. 另外開一個 hpfeeds-client 發佈訊息

./hpfeeds-client -i ident -s secret --host <your_broker_host> -p <your_broker_port> -c chan1 publish "Hello World"

4. 查看 subscribe 的 hpfeeds-client 是否有得到訊息，有的話就是成功了


### 不同的 hpfeeds-client 範例

可以在 `examples/` 資料夾底下找到各種不一樣的 hpfeeds-client 的範例，並且依照自己不同的需求改寫。

例如：

basic_mongodb.py 會將收到的資料存進 mongodb
