# -*- coding: utf-8 -*-

import shutil

import os, datetime, re, hashlib
import logging
from odoo import models, tools, fields, api, _

_logger = logging.getLogger(__name__)


class FlightLog(models.Model):
    _name = 'file.scanner'
    _description = 'file scanner'

    size = fields.Integer(string="Kilobytes")
    path = fields.Char(required=True)
    mtime = fields.Datetime()
    ctime = fields.Datetime()

    parsed_date = fields.Date(
        compute='_compute_details',
        store=True,
    )

    date = fields.Date(
        compute='_compute_details',
        store=True,
        readonly=False,
    )

    suffix = fields.Char(
        compute='_compute_details',
        store=True,
    )

    fname = fields.Char(
        compute='_compute_details',
        store=True,
    )

    parent = fields.Char(
        compute='_compute_details',
        store=True,
    )

    md5hexdigest = fields.Char()

    def _get_md5hexdigest(self):
        if not self.md5hexdigest:
            with open(self.path, "rb") as f:
                file_hash = hashlib.md5()
                while chunk := f.read(8192):
                    file_hash.update(chunk)
            self.md5hexdigest = file_hash.hexdigest()
        return self.md5hexdigest

    def export(self, path='/run/media/elmeri/Portable4T/Memories/PicsAndVids'):
        exported_md5 = set()
        for i, record in enumerate(self, start=1):
            if i % 1000 == 0:
                _logger.info(f"Export {i}/{len(self)}")
            dir = os.path.join(path, str(record.date.year), record.parent)
            md5 = record._get_md5hexdigest()
            os.makedirs(dir, exist_ok=True)
            fname = record.fname
            date = record.date.strftime('%Y-%m-%d')
            if not fname.startswith(date):
                fname = f'{date}-{fname}'

            dst = os.path.join(dir, fname)
            if md5 in exported_md5:
                _logger.error("Duplicate: %s", dst)
            elif os.path.exists(dst):
                _logger.error("Already exists: %s", dst)
            else:
                shutil.copy2(record.path, dst)
            exported_md5.add(md5)

    def scan(self, scanpath='/run/media/elmeri/Portable4T/Memories'):
        existing = {r.path: r for r in self.search([])}
        exclude = ['.git', 'gocryptfs', 'GoPro', 'Garmin']
        for root, dirs, files in os.walk(scanpath, topdown=True):
            _logger.info("Existing %s. Scan %s", len(existing), root)
            dirs[:] = [d for d in dirs if d not in exclude and not d.startswith('.')]
            for fname in files:
                path = os.path.join(root, fname)
                (mode, ino, dev, nlink, uid, gid, size, atime, mtime, ctime) = os.stat(path)
                vals = {
                    'size': size/1000,
                    'mtime': datetime.datetime.fromtimestamp(mtime),
                    'ctime': datetime.datetime.fromtimestamp(ctime),
                    'fname': fname,
                }
                if path in existing:
                    existing[path].write(vals)
                else:
                    existing[path] = self.with_context(default_path=path).create(vals)
            self.env.cr.commit()


    def _parse_date(self):
        datepatterns = [
            (r'(20\d\d-\d\d-\d\d)', '%Y-%m-%d'),
            (r'(20\d\d \d\d \d\d)', '%Y %m %d'),
            (r'(\d\d-\d\d-20\d\d)', '%m-%d-%Y'),
            (r'(20\d\d-\d\d)', '%Y-%m'),
            (r'(20\d{6})[^\d]', '%Y%m%d'),
            (r'[^\d](20\d{6})', '%Y%m%d'),
            (r'[^\d](20\d{4})', '%Y%m'),
        ]
        for part in self.path.split('/')[::-1]:
            for (pattern, fmt) in datepatterns:
                for match in re.findall(pattern, part):
                    try:
                        parsed_date = datetime.datetime.strptime(match, fmt).date()
                    except Exception as error:
                        _logger.error(f'{match} did not convert into {fmt}: {error}')
                        continue

                    if parsed_date > self.mtime.date(): # Can not be taken before time it was last modified
                        _logger.error(f'{self.path} converted into {parsed_date} which is after {self.mtime}.')
                        continue

                    return parsed_date


    @api.depends('path')
    def _compute_details(self):

        for record in self:
            record.suffix = record.path.split('.')[-1].lower() if '.' in record.path else False

            idx = -2
            sec = record.path.split('/')[idx].lower()
            while re.fullmatch(r'[\w]?[\d_\-\s]+', sec):
                sec = record.path.split('/')[idx].lower()
                idx -= 1

            record.parent = sec

            parsed_date = record._parse_date()
            if not parsed_date and str(record.mtime.year) in record.path:
                parsed_date = record.mtime.date()

            record.parsed_date = parsed_date
            record.date = parsed_date or record.mtime.date()
