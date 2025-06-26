#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import hashlib
import logging
import smtplib

import loader, services


def send_by_smtp(mail, from_, to, timeout, port, encryption, relay, username, password):
    if encryption == 'ssl':
        server = smtplib.SMTP_SSL(relay, port, timeout=timeout)
    else:
        server = smtplib.SMTP(relay, port, timeout=timeout)
        if encryption == 'tls':
            server.starttls()
    server.login(username, password)
    server.sendmail(from_, to, mail)
    server.quit()


class MailService(services.AsyncService):
    def create_mail(self, sender, to, subject, body, attachment_data, attachment_name):
        from email.header import Header
        from email.mime.application import MIMEApplication
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.utils import formatdate

        mail = MIMEMultipart()
        mail["From"] = sender
        mail["To"] = to
        mail["Subject"] = Header(subject, "utf-8")
        mail["Date"] = formatdate(localtime=True)
        mail["Message-ID"] = "<tencent_%s@qq.com>" % hashlib.md5(mail.as_string().encode("UTF-8")).hexdigest()
        mail.preamble = "You will not see this in a MIME-aware mail reader.\n"

        if body is not None:
            msg = MIMEText(body, "plain", "utf-8")
            mail.attach(msg)

        if attachment_data is not None:
            name = Header(attachment_name, "utf-8").encode()
            msg = MIMEApplication(attachment_data, "octet-stream", charset="utf-8", name=name)
            msg.add_header("Content-Disposition", "attachment", filename=name)
            mail.attach(msg)
        return mail.as_string()

    # 系统配置时需要以阻塞模式测试邮件功能
    def do_send_mail(self, sender, to, subject, body, attachment_data=None, attachment_name=None, **kwargs):
        CONF = loader.get_settings()

        timeout = kwargs.get("timeout", 20)
        smtp_port = 465
        relay = kwargs.get("relay", CONF["smtp_server"])
        if ':' in relay:
            relay, smtp_port = relay.split(":")
        username = kwargs.get("username", CONF["smtp_username"])
        password = kwargs.get("password", CONF["smtp_password"])
        encryption = kwargs.get("encryption", CONF["smtp_encryption"]).lower()
        mail = self.create_mail(sender, to, subject, body, attachment_data, attachment_name)

        # connect to smtp server and send mail
        try:
            send_by_smtp(mail, sender, to, timeout, smtp_port, encryption, relay, username, password)
        except Exception as e:
            logging.error(f"Failed to send email: {e}")
            return False
        return True

    @services.AsyncService.register_service
    def send_mail(self, sender, to, subject, body, attachment_data=None, attachment_name=None, **kwargs):
        return self.do_send_mail(sender, to, subject, body, attachment_data, attachment_name, **kwargs)
