from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from . import access
from .models import ProjectImage, StudentProject, Technology

MAX_TECHNOLOGIES = 15
MAX_IMAGES = 12
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def _person(user) -> dict | None:
    if user is None:
        return None
    profile = getattr(user, "teacher_profile", None)
    return {"id": user.pk, "full_name": user.get_full_name() or user.username, "image": profile.image if profile else None}


def _media_url(request, field) -> str | None:
    if not field:
        return None
    url = field.url
    return request.build_absolute_uri(url) if request is not None else url


def student_ref(student) -> dict:
    return {"id": student.pk, "full_name": str(student), "status": student.status}


def group_ref(group) -> dict | None:
    return {"id": group.pk, "name": group.name} if group is not None else None


def cover_of(project: StudentProject) -> ProjectImage | None:
    images = list(project.images.all())  # prefetched
    return next((i for i in images if i.is_cover), images[0] if images else None)


class ProjectImageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectImage
        fields = ["id", "url", "is_cover", "order"]

    def get_url(self, obj) -> str | None:
        return _media_url(self.context.get("request"), obj.image)


class ProjectListSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    author = serializers.SerializerMethodField()
    technologies = serializers.SerializerMethodField()
    cover_url = serializers.SerializerMethodField()
    images_count = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = StudentProject
        fields = ["id", "title", "short_description", "project_date", "status", "rating", "technologies",
                  "student", "group", "author", "cover_url", "images_count", "can_edit", "created_at", "updated_at"]

    def get_student(self, obj) -> dict:
        return student_ref(obj.student)

    def get_group(self, obj) -> dict | None:
        return group_ref(obj.group)

    def get_author(self, obj) -> dict | None:
        person = _person(obj.created_by)
        if person is not None:
            person["image"] = _media_url(self.context.get("request"), person["image"])
        return person

    def get_technologies(self, obj) -> list[str]:
        return sorted(t.name for t in obj.technologies.all())

    def get_cover_url(self, obj) -> str | None:
        cover = cover_of(obj)
        return _media_url(self.context.get("request"), cover.image) if cover else None

    def get_images_count(self, obj) -> int:
        return len(obj.images.all())

    def get_can_edit(self, obj) -> bool:
        return access.can_edit(self.context["request"].user, obj)


class ProjectDetailSerializer(ProjectListSerializer):
    images = ProjectImageSerializer(many=True, read_only=True)
    course = serializers.SerializerMethodField()

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + [
            "description", "github_url", "demo_url", "figma_url", "trainer_comment", "images", "course",
        ]

    def get_course(self, obj) -> dict | None:
        course = obj.group.course if obj.group_id else None
        return {"id": course.pk, "name": course.name} if course else None


class ProjectWriteSerializer(serializers.ModelSerializer):
    """Create / update. The group always follows the selected student (the
    trainer never types it), and the student must be one the user may pick."""

    student = serializers.PrimaryKeyRelatedField(queryset=access.selectable_students(None))
    technologies = serializers.ListField(child=serializers.CharField(max_length=50, trim_whitespace=True),
                                         required=False, max_length=MAX_TECHNOLOGIES)

    class Meta:
        model = StudentProject
        fields = ["student", "title", "short_description", "description", "technologies", "project_date",
                  "github_url", "demo_url", "figma_url", "trainer_comment", "rating", "status"]
        extra_kwargs = {"title": {"error_messages": {"blank": "Укажите название проекта."}}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        self.fields["student"].queryset = access.selectable_students(request.user if request else None)

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Укажите название проекта.")
        return value

    def validate_student(self, student):
        if student.group_id is None:
            raise serializers.ValidationError("Студент не состоит в группе.")
        return student

    def validate_technologies(self, names: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for name in names:
            name = " ".join(name.split())
            if name and name.lower() not in seen:
                seen[name.lower()] = name
        return list(seen.values())

    def _set_technologies(self, project, names):
        if names is None:
            return
        techs = []
        for name in names:
            tech = Technology.objects.filter(name__iexact=name).first() or Technology.objects.create(name=name)
            techs.append(tech)
        project.technologies.set(techs)

    @transaction.atomic
    def create(self, validated_data):
        names = validated_data.pop("technologies", [])
        student = validated_data["student"]
        project = StudentProject.objects.create(group=student.group, **validated_data)
        self._set_technologies(project, names)
        return project

    @transaction.atomic
    def update(self, instance, validated_data):
        names = validated_data.pop("technologies", None)
        student = validated_data.get("student")
        if student is not None and student.pk != instance.student_id:
            instance.group = student.group
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        self._set_technologies(instance, names)
        return instance


class ProjectImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(error_messages={
        "invalid_image": "Файл не является изображением JPG, PNG или WEBP.",
        "required": "Выберите изображение.",
    })
    is_cover = serializers.BooleanField(required=False, default=False)

    def validate_image(self, image):
        if image.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError("Изображение больше 10 МБ.")
        fmt = getattr(getattr(image, "image", None), "format", None)
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise serializers.ValidationError("Поддерживаются только JPG, PNG и WEBP.")
        return image
